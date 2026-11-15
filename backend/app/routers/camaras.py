"""Endpoints de consulta: cámaras, lecturas y lotes.

Exigen el JWT de usuario cuando `AUTH_REQUERIDA=1`; con la bandera apagada
(local y pruebas) quedan abiertos como antes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.core.auth import RestauranteId, get_current_user
from app.db.models import Camara, Lectura, Lote
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["consulta"], dependencies=[Depends(get_current_user)])

VENTANA_POR_DEFECTO = timedelta(hours=2)
LIMITE_LECTURAS = 5000

Db = Annotated[Session, Depends(get_db)]


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
    filas = db.execute(
        select(
            Lote.camara_id,
            func.sum(case((Lote.estado == "en_riesgo", Lote.costo_total_mxn), else_=0)),
            func.sum(case((Lote.estado != "merma", Lote.costo_total_mxn), else_=0)),
        )
        .join(Camara, Camara.id == Lote.camara_id)
        .where(Camara.restaurante_id == restaurante_id)
        .group_by(Lote.camara_id)
    ).all()
    riesgo = {camara_id: float(total or 0) for camara_id, total, _ in filas}
    inventario = {camara_id: float(total or 0) for camara_id, _, total in filas}
    lecturas = _ultimas_lecturas(db, camaras)

    return [
        {
            "id": camara.id,
            "nombre": camara.nombre,
            "rango_min_c": _flotante(camara.rango_min_c),
            "rango_max_c": _flotante(camara.rango_max_c),
            "min_para_riesgo": camara.min_para_riesgo,
            "min_para_merma": camara.min_para_merma,
            "estado": camara.estado,
            "ultima_lectura": _resumen_lectura(lecturas.get(camara.id)),
            "valor_en_riesgo_mxn": riesgo.get(camara.id, 0.0),
            "valor_inventario_mxn": inventario.get(camara.id, 0.0),
        }
        for camara in camaras
    ]


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
