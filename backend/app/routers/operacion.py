"""Alertas operativas, KPIs del dashboard y alertas de seguridad."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Alerta, AlertaSeguridad, Usuario
from app.db.session import get_db
from app.realtime.bus import bus
from app.schemas.operacion import (
    AlertaSalida,
    AlertaSeguridadSalida,
    KpisSalida,
    alerta_salida,
    alerta_seguridad_salida,
)
from app.services.kpis import calcular_kpis

router = APIRouter(prefix="/api", tags=["operacion"])

SesionDb = Annotated[Session, Depends(get_db)]


class AtenderEntrada(BaseModel):
    """Cuerpo de `POST /alertas/{id}/atender`; la nota es opcional."""

    nota: str | None = None


# Auth pendiente (fase posterior): estos endpoints quedan abiertos en local.
@router.get("/alertas", response_model=list[AlertaSalida])
def listar_alertas(
    db: SesionDb,
    activas: bool = False,
    limite: int = Query(50, ge=1, le=200),
) -> list[AlertaSalida]:
    """Lista las alertas de la más reciente a la más antigua.

    `activas` filtra las que siguen abiertas; `limite` acota cuántas se
    devuelven y por defecto son 50 (máximo 200).
    """
    consulta = select(Alerta).order_by(Alerta.abierta_en.desc(), Alerta.id.desc())
    if activas:
        consulta = consulta.where(Alerta.cerrada_en.is_(None))
    consulta = consulta.limit(limite)
    return [alerta_salida(alerta) for alerta in db.scalars(consulta).all()]


@router.post("/alertas/{alerta_id}/atender", response_model=AlertaSalida)
def atender_alerta(
    alerta_id: int,
    entrada: AtenderEntrada,
    db: SesionDb,
) -> AlertaSalida:
    """Marca quién atendió la alerta y cuándo; no la cierra.

    Es idempotente: si la alerta ya estaba atendida conserva `atendida_en` y
    `atendida_por` (para no empeorar el KPI de tiempo de respuesta) y solo
    actualiza la nota cuando viene en el cuerpo.
    """
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")
    if alerta.cerrada_en is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="La alerta ya está cerrada"
        )

    if alerta.atendida_en is not None:
        if entrada.nota is not None:
            alerta.nota = entrada.nota
            db.commit()
            bus.publicar("alerta_cerrada", alerta_salida(alerta).model_dump())
        return alerta_salida(alerta)

    # Auth pendiente (fase posterior): aquí irá el usuario del JWT. Mientras tanto
    # se atribuye al primer `jefe_cocina`, que en el seed es el usuario `jefe`.
    jefe = db.scalar(
        select(Usuario).where(Usuario.rol == "jefe_cocina").order_by(Usuario.id).limit(1)
    )
    if jefe is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "No hay un usuario con rol jefe_cocina; carga el seed (usuario «jefe») "
                "para poder atender alertas."
            ),
        )

    alerta.atendida_por = jefe.id
    alerta.atendida_en = utcnow()
    if entrada.nota is not None:
        alerta.nota = entrada.nota
    db.commit()

    # El contrato dice que `alerta_cerrada` también se manda cuando la atienden.
    salida = alerta_salida(alerta)
    bus.publicar("alerta_cerrada", salida.model_dump())
    return salida


# Auth pendiente (fase posterior): este endpoint queda abierto en local.
@router.get("/kpis", response_model=KpisSalida)
def obtener_kpis(db: SesionDb) -> KpisSalida:
    """Calcula los KPIs del dashboard a partir de lecturas, alertas y lotes."""
    return KpisSalida(**calcular_kpis(db))


# Auth pendiente (fase posterior): este endpoint queda abierto en local.
@router.get("/seguridad/alertas", response_model=list[AlertaSeguridadSalida])
def listar_alertas_seguridad(
    db: SesionDb,
) -> list[AlertaSeguridadSalida]:
    """Devuelve las últimas 20 alertas del detector SIEM."""
    filas = db.scalars(
        select(AlertaSeguridad)
        .order_by(AlertaSeguridad.ts.desc(), AlertaSeguridad.id.desc())
        .limit(20)
    ).all()
    return [alerta_seguridad_salida(fila) for fila in filas]
