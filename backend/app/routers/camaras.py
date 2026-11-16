"""Endpoints de consulta: cámaras, lecturas y lotes.

Exigen el JWT de usuario cuando `AUTH_REQUERIDA=1`; con la bandera apagada
(local y pruebas) quedan abiertos como antes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.auth import RestauranteId, get_current_user, require_rol
from app.db.base import utcnow
from app.db.models import Alerta, Camara, Lectura, Lote, Sensor, Usuario
from app.db.session import get_db
from app.erp import reglas
from app.erp.procesador import TIPO_ALERTA_TEMPERATURA
from app.realtime.bus import bus
from app.schemas.camaras import CamaraActualizacion, CamaraCreacion
from app.schemas.operacion import alerta_salida

router = APIRouter(prefix="/api", tags=["consulta"], dependencies=[Depends(get_current_user)])

VENTANA_POR_DEFECTO = timedelta(hours=2)
LIMITE_LECTURAS = 5000
MENSAJE_CAMARA_CON_DATOS = (
    "La cámara tiene datos asociados; desactívala o elimina primero sus sensores."
)

Db = Annotated[Session, Depends(get_db)]
Dueno = Annotated[Usuario | None, Depends(require_rol("dueno"))]


def camara_del_restaurante(
    db: Session,
    camara_id: int,
    restaurante_id: int,
    *,
    detalle: str = "Cámara no encontrada",
) -> Camara:
    """Carga la cámara o responde 404 si no existe o es de otro restaurante.

    El 404 (no 403) evita filtrar si una cámara de otro tenant existe. Vive aquí
    para que cada endpoint nuevo reutilice la misma verificación.
    """
    camara = db.get(Camara, camara_id)
    if camara is None or camara.restaurante_id != restaurante_id:
        raise HTTPException(status_code=404, detail=detalle)
    return camara


def _flotante(valor: Decimal | None) -> float | None:
    """Convierte numeric de Postgres a float para que el JSON sea numérico."""
    return None if valor is None else float(valor)


def _ultimas_lecturas(db: Session, camaras: Sequence[Camara]) -> dict[int, Lectura]:
    """Resuelve la última lectura de todas las cámaras en dos consultas como máximo.

    Primero usa los atajos `ultima_lectura_id` de las cámaras y, para las que
    quedan sin lectura, trae la más reciente por cámara con `DISTINCT ON`.
    """
    ids = [camara.ultima_lectura_id for camara in camaras if camara.ultima_lectura_id]
    por_id: dict[int, Lectura] = {}
    if ids:
        por_id = {
            lectura.id: lectura
            for lectura in db.execute(select(Lectura).where(Lectura.id.in_(ids))).scalars().all()
        }
    lecturas = {
        camara.id: por_id[camara.ultima_lectura_id]
        for camara in camaras
        if camara.ultima_lectura_id in por_id
    }

    sin_lectura = [camara.id for camara in camaras if camara.id not in lecturas]
    if sin_lectura:
        recientes = (
            db.execute(
                select(Lectura)
                .where(Lectura.camara_id.in_(sin_lectura))
                .order_by(Lectura.camara_id, Lectura.recibida_en.desc())
                .ext(distinct_on(Lectura.camara_id))
            )
            .scalars()
            .all()
        )
        lecturas.update({lectura.camara_id: lectura for lectura in recientes})
    return lecturas


def _resumen_lectura(lectura: Lectura | None) -> dict[str, Any] | None:
    """Arma el objeto `ultima_lectura` del contrato (o null si no hay)."""
    if lectura is None:
        return None
    return {
        "ts": lectura.ts.isoformat(),
        "temperatura_c": _flotante(lectura.temperatura_c),
        "humedad_pct": _flotante(lectura.humedad_pct),
        "puerta_abierta": lectura.puerta_abierta,
    }


def _salida_camara(
    camara: Camara,
    lectura: Lectura | None = None,
    valor_en_riesgo_mxn: float = 0.0,
    valor_inventario_mxn: float = 0.0,
) -> dict[str, Any]:
    """Shape de cámara compartido por `GET`, el alta y la edición."""
    return {
        "id": camara.id,
        "nombre": camara.nombre,
        "rango_min_c": _flotante(camara.rango_min_c),
        "rango_max_c": _flotante(camara.rango_max_c),
        "min_para_riesgo": camara.min_para_riesgo,
        "min_para_merma": camara.min_para_merma,
        "estado": camara.estado,
        "ultima_lectura": _resumen_lectura(lectura),
        "valor_en_riesgo_mxn": valor_en_riesgo_mxn,
        "valor_inventario_mxn": valor_inventario_mxn,
    }


def _valores_por_camara(
    db: Session, camara_ids: Sequence[int]
) -> tuple[dict[int, float], dict[int, float]]:
    """Riesgo e inventario por cámara en una sola query agregada.

    Los ids vienen de cámaras ya filtradas por restaurante, así que no hace
    falta volver a unir con `camaras`.
    """
    if not camara_ids:
        return {}, {}
    filas = db.execute(
        select(
            Lote.camara_id,
            func.sum(case((Lote.estado == "en_riesgo", Lote.costo_total_mxn), else_=0)),
            func.sum(case((Lote.estado != "merma", Lote.costo_total_mxn), else_=0)),
        )
        .where(Lote.camara_id.in_(camara_ids))
        .group_by(Lote.camara_id)
    ).all()
    riesgo = {camara_id: float(total or 0) for camara_id, total, _ in filas}
    inventario = {camara_id: float(total or 0) for camara_id, _, total in filas}
    return riesgo, inventario


def _salida_camara_con_valores(db: Session, camara: Camara) -> dict[str, Any]:
    """Cámara con sus valores reales; lo usa la edición (el alta nace en cero)."""
    riesgo, inventario = _valores_por_camara(db, [camara.id])
    lectura = _ultimas_lecturas(db, [camara]).get(camara.id)
    return _salida_camara(
        camara,
        lectura,
        riesgo.get(camara.id, 0.0),
        inventario.get(camara.id, 0.0),
    )


def _tiene_dependencias(db: Session, camara_id: int) -> bool:
    """Una sola query con EXISTS: cualquier fila asociada bloquea el borrado."""
    return bool(
        db.scalar(
            select(
                or_(
                    exists().where(Sensor.camara_id == camara_id),
                    exists().where(Lote.camara_id == camara_id),
                    exists().where(Lectura.camara_id == camara_id),
                    exists().where(Alerta.camara_id == camara_id),
                )
            )
        )
    )


def _reconciliar_estado(db: Session, camara: Camara) -> Alerta | None:
    """Recalcula estado/ventanas con la configuración nueva y cierra alertas si aplica.

    Se llama después de aplicar el PATCH y antes del commit. No abre alertas: la
    siguiente lectura o el tick deciden con las reglas normales. Regresa la
    alerta de temperatura que se cerró, para publicarla tras el commit.
    """
    ultima = db.scalars(
        select(Lectura)
        .where(Lectura.camara_id == camara.id)
        .order_by(Lectura.recibida_en.desc())
        .limit(1)
    ).first()
    alerta_abierta = db.scalars(
        select(Alerta).where(
            Alerta.camara_id == camara.id,
            Alerta.tipo == TIPO_ALERTA_TEMPERATURA,
            Alerta.cerrada_en.is_(None),
        )
    ).first()

    if ultima is None:
        camara.estado = "en_rango"
        camara.fuera_de_rango_desde = None
        camara.puerta_abierta_desde = None
        cerrada = alerta_abierta
    else:
        en_rango = reglas.esta_en_rango(
            float(ultima.temperatura_c),
            float(camara.rango_min_c),
            float(camara.rango_max_c),
        )
        if en_rango:
            camara.fuera_de_rango_desde = None
            cerrada = alerta_abierta
        else:
            if camara.fuera_de_rango_desde is None:
                camara.fuera_de_rango_desde = utcnow()
            cerrada = None

        if ultima.puerta_abierta:
            if camara.puerta_abierta_desde is None:
                camara.puerta_abierta_desde = ultima.recibida_en
        else:
            camara.puerta_abierta_desde = None

        lotes = list(db.scalars(select(Lote).where(Lote.camara_id == camara.id)))
        camara.estado = reglas.estado_camara(
            en_rango=en_rango,
            puerta_abierta=ultima.puerta_abierta,
            lotes_en_riesgo=sum(1 for lote in lotes if lote.estado == "en_riesgo"),
            lotes_en_merma=sum(1 for lote in lotes if lote.estado == "merma"),
        )

    if cerrada is not None:
        cerrada.cerrada_en = utcnow()
    return cerrada


@router.get("/camaras")
def listar_camaras(db: Db, restaurante_id: RestauranteId) -> list[dict[str, Any]]:
    """Lista las cámaras del restaurante con su última lectura y el valor de sus lotes.

    `valor_en_riesgo_mxn` solo suma los lotes `en_riesgo`;
    `valor_inventario_mxn` suma todo el inventario salvo lo que ya es merma.
    """
    camaras = (
        db.execute(
            select(Camara)
            .where(Camara.restaurante_id == restaurante_id)
            .order_by(Camara.id)
        )
        .scalars()
        .all()
    )
    riesgo, inventario = _valores_por_camara(db, [camara.id for camara in camaras])
    lecturas = _ultimas_lecturas(db, camaras)

    return [
        _salida_camara(
            camara,
            lecturas.get(camara.id),
            riesgo.get(camara.id, 0.0),
            inventario.get(camara.id, 0.0),
        )
        for camara in camaras
    ]


@router.post("/camaras", status_code=status.HTTP_201_CREATED)
def crear_camara(
    datos: CamaraCreacion,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: Dueno,
) -> dict[str, Any]:
    """Crea una cámara en el restaurante del JWT, sin sensores ni lecturas.

    Nace con `es_demo=False`: el tick simulado solo alimenta las cámaras del seed.
    """
    camara = Camara(
        restaurante_id=restaurante_id,
        es_demo=False,
        nombre=datos.nombre,
        rango_min_c=datos.rango_min_c,
        rango_max_c=datos.rango_max_c,
        min_para_riesgo=datos.min_para_riesgo,
        min_para_merma=datos.min_para_merma,
        estado="en_rango",
    )
    db.add(camara)
    db.commit()
    return _salida_camara(camara)


@router.patch("/camaras/{id}")
def actualizar_camara(
    id: int,
    datos: CamaraActualizacion,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: Dueno,
) -> dict[str, Any]:
    """Actualiza la configuración y reconcilia el estado con los valores nuevos.

    Los campos de sistema (`estado`, `ultima_lectura_id`, `restaurante_id`) no
    existen en el body y el esquema los rechaza con 422. La configuración
    resultante se valida con `CamaraCreacion`, la misma regla del alta.
    """
    camara = camara_del_restaurante(db, id, restaurante_id)
    cambios = datos.model_dump(exclude_unset=True)
    alerta_cerrada = None
    if cambios:
        guardada = {
            "nombre": camara.nombre,
            "rango_min_c": camara.rango_min_c,
            "rango_max_c": camara.rango_max_c,
            "min_para_riesgo": camara.min_para_riesgo,
            "min_para_merma": camara.min_para_merma,
        }
        try:
            validada = CamaraCreacion.model_validate({**guardada, **cambios})
        except ValidationError as error:
            raise RequestValidationError(error.errors()) from error

        for campo in cambios:
            setattr(camara, campo, getattr(validada, campo))
        alerta_cerrada = _reconciliar_estado(db, camara)
        db.commit()
        if alerta_cerrada is not None:
            bus.publicar(
                "alerta_cerrada",
                alerta_salida(alerta_cerrada).model_dump(),
                camara.restaurante_id,
            )

    return _salida_camara_con_valores(db, camara)


@router.delete("/camaras/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_camara(
    id: int,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: Dueno,
) -> Response:
    """Elimina una cámara solo si no tiene sensores, lotes, lecturas ni alertas."""
    camara = camara_del_restaurante(db, id, restaurante_id)
    if _tiene_dependencias(db, camara.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MENSAJE_CAMARA_CON_DATOS,
        )
    db.delete(camara)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/camaras/{id}/lecturas")
def listar_lecturas(
    id: int,
    db: Db,
    restaurante_id: RestauranteId,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> list[dict[str, Any]]:
    """Lecturas de una cámara; sin rango, las últimas 2 horas por `recibida_en`.

    Se piden las más recientes (hasta `LIMITE_LECTURAS`) y se responden en orden
    ascendente, que es como la gráfica las dibuja. Una cámara de otro restaurante
    responde 404, igual que una inexistente: no se filtra su existencia.
    """
    camara_del_restaurante(db, id, restaurante_id)

    if hasta is None:
        hasta = datetime.now(UTC)
    if desde is None:
        desde = hasta - VENTANA_POR_DEFECTO

    filas = (
        db.execute(
            select(Lectura)
            .where(
                Lectura.camara_id == id,
                Lectura.recibida_en >= desde,
                Lectura.recibida_en <= hasta,
            )
            .order_by(Lectura.recibida_en.desc())
            .limit(LIMITE_LECTURAS)
        )
        .scalars()
        .all()
    )
    lecturas = list(reversed(filas))

    return [
        {
            "id": lectura.id,
            "ts": lectura.ts.isoformat(),
            "recibida_en": lectura.recibida_en.isoformat(),
            "temperatura_c": _flotante(lectura.temperatura_c),
            "humedad_pct": _flotante(lectura.humedad_pct),
            "puerta_abierta": lectura.puerta_abierta,
            "sospechosa": lectura.sospechosa,
        }
        for lectura in lecturas
    ]


@router.get("/lotes")
def listar_lotes(
    db: Db,
    restaurante_id: RestauranteId,
    camara_id: int | None = None,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    """Lotes del restaurante, opcionalmente filtrados por cámara y estado."""
    if camara_id is not None:
        camara_del_restaurante(db, camara_id, restaurante_id)

    consulta = (
        select(Lote)
        .join(Camara, Camara.id == Lote.camara_id)
        .where(Camara.restaurante_id == restaurante_id)
    )
    if camara_id is not None:
        consulta = consulta.where(Lote.camara_id == camara_id)
    if estado is not None:
        consulta = consulta.where(Lote.estado == estado)
    lotes = db.execute(consulta.order_by(Lote.id)).scalars().all()

    return [
        {
            "id": lote.id,
            "producto": lote.producto,
            "camara_id": lote.camara_id,
            "cantidad": _flotante(lote.cantidad),
            "unidad": lote.unidad,
            "costo_total_mxn": _flotante(lote.costo_total_mxn),
            "caducidad": lote.caducidad.isoformat(),
            "estado": lote.estado,
        }
        for lote in lotes
    ]
