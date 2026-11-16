"""Inventario: consulta, CRUD de lotes y marca manual de merma."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import RestauranteId, get_current_user, require_rol
from app.db.base import utcnow
from app.db.models import Camara, Lote, Usuario
from app.db.session import get_db
from app.routers.camaras import camara_del_restaurante
from app.schemas.lotes import LoteActualizacion, LoteCreacion
from app.schemas.utils import iso

router = APIRouter(
    prefix="/api",
    tags=["inventario"],
    dependencies=[Depends(get_current_user)],
)

Db = Annotated[Session, Depends(get_db)]
DuenoOjefe = Annotated[Usuario | None, Depends(require_rol("dueno", "jefe_cocina"))]

MENSAJE_LOTE_EN_MERMA = (
    "El lote ya está en merma; no se puede eliminar del historial."
)


def _flotante(valor: Decimal | None) -> float | None:
    """Convierte un numeric de Postgres a float para que el JSON sea numérico."""
    return None if valor is None else float(valor)


def _salida_lote(lote: Lote) -> dict[str, Any]:
    """Shape de lote compartido por `GET`, el alta, la edición y la merma."""
    return {
        "id": lote.id,
        "producto": lote.producto,
        "camara_id": lote.camara_id,
        "cantidad": _flotante(lote.cantidad),
        "unidad": lote.unidad,
        "costo_total_mxn": _flotante(lote.costo_total_mxn),
        "caducidad": lote.caducidad.isoformat(),
        "estado": lote.estado,
        "merma_en": iso(lote.merma_en),
    }


def lote_del_restaurante(
    db: Session,
    lote_id: int,
    restaurante_id: int,
) -> Lote:
    """Carga el lote o responde 404 si no existe o su cámara es de otro tenant."""
    lote = db.get(Lote, lote_id)
    if lote is None:
        raise HTTPException(status_code=404, detail="Lote no encontrado")
    camara_del_restaurante(
        db,
        lote.camara_id,
        restaurante_id,
        detalle="Lote no encontrado",
    )
    return lote


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

    return [_salida_lote(lote) for lote in lotes]


@router.post("/lotes", status_code=status.HTTP_201_CREATED)
def crear_lote(
    datos: LoteCreacion,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: DuenoOjefe,
) -> dict[str, Any]:
    """Crea un lote en una cámara del restaurante; nace `ok` y sin merma."""
    camara_del_restaurante(db, datos.camara_id, restaurante_id)
    lote = Lote(
        producto=datos.producto,
        camara_id=datos.camara_id,
        cantidad=datos.cantidad,
        unidad=datos.unidad,
        costo_total_mxn=datos.costo_total_mxn,
        caducidad=datos.caducidad,
        estado="ok",
        merma_en=None,
    )
    db.add(lote)
    db.commit()
    return _salida_lote(lote)


@router.patch("/lotes/{id}")
def actualizar_lote(
    id: int,
    datos: LoteActualizacion,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: DuenoOjefe,
) -> dict[str, Any]:
    """Actualiza inventario; el estado y `merma_en` no se tocan desde aquí.

    La configuración resultante se valida con `LoteCreacion` (la misma regla del
    alta) y, si se mueve a otra cámara, esa cámara debe ser del tenant.
    """
    lote = lote_del_restaurante(db, id, restaurante_id)
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        return _salida_lote(lote)

    if "camara_id" in cambios:
        camara_del_restaurante(db, cambios["camara_id"], restaurante_id)

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
        raise RequestValidationError(error.errors()) from error

    for campo in cambios:
        setattr(lote, campo, getattr(validado, campo))
    db.commit()
    return _salida_lote(lote)


@router.delete("/lotes/{id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_lote(
    id: int,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: DuenoOjefe,
) -> Response:
    """Elimina lotes `ok` o `en_riesgo`; la merma es historial y no se borra."""
    lote = lote_del_restaurante(db, id, restaurante_id)
    if lote.estado == "merma":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MENSAJE_LOTE_EN_MERMA,
        )
    db.delete(lote)
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
    devuelve el lote.
    """
    lote = lote_del_restaurante(db, id, restaurante_id)
    if lote.estado != "merma":
        lote.estado = "merma"
        lote.merma_en = utcnow()
        db.commit()
    return _salida_lote(lote)
