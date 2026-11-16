"""Inventario: consulta, CRUD de lotes y marca manual de merma."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import RestauranteId, get_current_user, require_rol
from app.db.base import utcnow
from app.db.models import Camara, Lectura, Lote, Usuario
from app.db.session import get_db
from app.erp import reglas
from app.routers.camaras import camara_del_restaurante
from app.schemas.lotes import LoteActualizacion, LoteCreacion
from app.schemas.operacion import lote_salida
from app.schemas.utils import errores_de_validacion

router = APIRouter(
    prefix="/api",
    tags=["inventario"],
    dependencies=[Depends(get_current_user)],
)

Db = Annotated[Session, Depends(get_db)]
DuenoOjefe = Annotated[Usuario | None, Depends(require_rol("dueno", "jefe_cocina"))]

MENSAJE_LOTE_EN_MERMA_ELIMINAR = (
    "El lote ya está en merma; no se puede eliminar del historial."
)
MENSAJE_LOTE_EN_MERMA_EDITAR = (
    "El lote ya está en merma; no se puede modificar del historial."
)


def lote_del_restaurante(
    db: Session,
    lote_id: int,
    restaurante_id: int,
    *,
    for_update: bool = False,
) -> Lote:
    """Carga el lote y su cámara en una sola query, o responde 404.

    Con `for_update` bloquea el lote **y la cámara** (`FOR UPDATE` sobre el
    join), el mismo lock que toma la ingesta de telemetría antes de tocar los
    lotes: así una merma manual y una lectura concurrente se serializan.
    """
    consulta = (
        select(Lote)
        .join(Camara, Camara.id == Lote.camara_id)
        .where(Lote.id == lote_id, Camara.restaurante_id == restaurante_id)
    )
    if for_update:
        consulta = consulta.with_for_update()
    lote = db.scalars(consulta).first()
    if lote is None:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    return lote


def _estado_lote_para_camara(camara: Camara, ahora: datetime) -> tuple[str, datetime | None]:
    """Estado inicial de un lote según la ventana actual de su cámara.

    Si la cámara está en rango, el lote nace `ok`. Si lleva fuera de rango, se
    aplican los mismos umbrales del ERP (riesgo/merma) para no esperar a la
    siguiente lectura: un lote nuevo en una cámara ya en merma nace en merma.
    """
    if camara.fuera_de_rango_desde is None:
        return "ok", None

    escala = get_settings().escala_tiempo
    if reglas.debe_marcar_merma(
        camara.fuera_de_rango_desde,
        ahora,
        camara.min_para_merma,
        escala,
    ):
        return "merma", ahora
    if reglas.debe_abrir_alerta_temperatura(
        camara.fuera_de_rango_desde,
        ahora,
        camara.min_para_riesgo,
        escala,
    ):
        return "en_riesgo", None
    return "ok", None


def _recalcular_estado_camara(db: Session, camara: Camara) -> None:
    """Recalcula `camara.estado` con la última lectura y los lotes actuales.

    No abre ni cierra alertas: eso lo hacen la ingesta y el PATCH de cámara.
    """
    ultima = db.scalars(
        select(Lectura)
        .where(Lectura.camara_id == camara.id)
        .order_by(Lectura.recibida_en.desc())
        .limit(1)
    ).first()
    lotes = list(db.scalars(select(Lote).where(Lote.camara_id == camara.id)))

    en_rango = True
    puerta_abierta = False
    if ultima is not None:
        en_rango = reglas.esta_en_rango(
            float(ultima.temperatura_c),
            float(camara.rango_min_c),
            float(camara.rango_max_c),
        )
        puerta_abierta = ultima.puerta_abierta

    camara.estado = reglas.estado_camara(
        en_rango=en_rango,
        puerta_abierta=puerta_abierta,
        lotes_en_riesgo=sum(1 for lote in lotes if lote.estado == "en_riesgo"),
        lotes_en_merma=sum(1 for lote in lotes if lote.estado == "merma"),
    )


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

    return [lote_salida(lote).model_dump() for lote in lotes]


@router.post("/lotes", status_code=status.HTTP_201_CREATED)
def crear_lote(
    datos: LoteCreacion,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: DuenoOjefe,
) -> dict[str, Any]:
    """Crea un lote en una cámara del restaurante.

    El estado inicial sale de la ventana actual de la cámara (ok, en riesgo o
    merma) y la cámara destino se bloquea para serializar con la telemetría.
    """
    camara = camara_del_restaurante(
        db,
        datos.camara_id,
        restaurante_id,
        for_update=True,
    )
    estado, merma_en = _estado_lote_para_camara(camara, utcnow())
    lote = Lote(
        producto=datos.producto,
        camara_id=camara.id,
        cantidad=datos.cantidad,
        unidad=datos.unidad,
        costo_total_mxn=datos.costo_total_mxn,
        caducidad=datos.caducidad,
        estado=estado,
        merma_en=merma_en,
    )
    db.add(lote)
    _recalcular_estado_camara(db, camara)
    db.commit()
    return lote_salida(lote).model_dump()


@router.patch("/lotes/{id}")
def actualizar_lote(
    id: int,
    datos: LoteActualizacion,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: DuenoOjefe,
) -> dict[str, Any]:
    """Actualiza inventario; la merma es historial y no se puede reescribir.

    La configuración resultante se valida con `LoteCreacion` (la misma regla del
    alta). Si cambia de cámara, esa cámara debe ser del tenant y el lote se
    reubica con el estado que corresponda a la ventana de la cámara destino.
    """
    lote = lote_del_restaurante(db, id, restaurante_id, for_update=True)
    if lote.estado == "merma":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MENSAJE_LOTE_EN_MERMA_EDITAR,
        )

    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        return lote_salida(lote).model_dump()

    camara_origen = db.get(Camara, lote.camara_id)
    camara_destino = None
    if cambios.get("camara_id") is not None and cambios["camara_id"] != lote.camara_id:
        camara_destino = camara_del_restaurante(
            db,
            cambios["camara_id"],
            restaurante_id,
            for_update=True,
        )

    guardado = {
        "producto": lote.producto,
        "camara_id": lote.camara_id,
        "cantidad": lote.cantidad,
        "unidad": lote.unidad,
        "costo_total_mxn": lote.costo_total_mxn,
        "caducidad": lote.caducidad,
    }
    try:
        validado = LoteCreacion.model_validate({**guardado, **cambios})
    except ValidationError as error:
        raise RequestValidationError(errores_de_validacion(error)) from error

    for campo in cambios:
        setattr(lote, campo, getattr(validado, campo))

    if camara_destino is not None:
        # El lote ya no está en la cámara origen: recalcula ambas y ajusta su
        # estado a la condición actual del destino.
        if lote.estado in ("ok", "en_riesgo"):
            estado, merma_en = _estado_lote_para_camara(camara_destino, utcnow())
            lote.estado = estado
            lote.merma_en = merma_en
        _recalcular_estado_camara(db, camara_origen)
        _recalcular_estado_camara(db, camara_destino)
    else:
        _recalcular_estado_camara(db, camara_origen)

    db.commit()
    return lote_salida(lote).model_dump()


@router.delete("/lotes/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_lote(
    id: int,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: DuenoOjefe,
) -> Response:
    """Elimina lotes `ok` o `en_riesgo`; la merma es historial y no se borra."""
    lote = lote_del_restaurante(db, id, restaurante_id, for_update=True)
    if lote.estado == "merma":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MENSAJE_LOTE_EN_MERMA_ELIMINAR,
        )
    camara = db.get(Camara, lote.camara_id)
    db.delete(lote)
    _recalcular_estado_camara(db, camara)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lotes/{id}/merma")
def marcar_merma(
    id: int,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: DuenoOjefe,
) -> dict[str, Any]:
    """Registra una pérdida manual conservando el lote en el historial.

    Es idempotente: si ya estaba en merma conserva la fecha original y solo
    devuelve el lote. El lock del lote+cámara serializa con la telemetría para
    que la merma no se pierda si una lectura concurrente la marca como `ok`.
    """
    lote = lote_del_restaurante(db, id, restaurante_id, for_update=True)
    if lote.estado != "merma":
        camara = db.get(Camara, lote.camara_id)
        lote.estado = "merma"
        lote.merma_en = utcnow()
        _recalcular_estado_camara(db, camara)
        db.commit()
    return lote_salida(lote).model_dump()
