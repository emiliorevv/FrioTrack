"""Alertas operativas, KPIs del dashboard y alertas de seguridad."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import RestauranteId, get_current_user, require_rol
from app.db.base import utcnow
from app.db.models import RESTAURANTE_DEMO_ID, Alerta, AlertaSeguridad, Usuario
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

router = APIRouter(prefix="/api", tags=["operacion"], dependencies=[Depends(get_current_user)])

SesionDb = Annotated[Session, Depends(get_db)]
JefeCocina = Annotated[Usuario | None, Depends(require_rol("jefe_cocina"))]


class AtenderEntrada(BaseModel):
    """Cuerpo de `POST /alertas/{id}/atender`; la nota es opcional."""

    nota: str | None = None


# Con AUTH_REQUERIDA=0 estos endpoints quedan abiertos; con 1 exigen JWT.
@router.get("/alertas", response_model=list[AlertaSalida])
def listar_alertas(
    db: SesionDb,
    restaurante_id: RestauranteId,
    activas: bool = False,
    limite: int = Query(50, ge=1, le=200),
) -> list[AlertaSalida]:
    """Lista las alertas del restaurante de la más reciente a la más antigua.

    `activas` filtra las que siguen abiertas; `limite` acota cuántas se
    devuelven y por defecto son 50 (máximo 200).
    """
    consulta = (
        select(Alerta)
        .where(Alerta.restaurante_id == restaurante_id)
        .order_by(Alerta.abierta_en.desc(), Alerta.id.desc())
    )
    if activas:
        consulta = consulta.where(Alerta.cerrada_en.is_(None))
    consulta = consulta.limit(limite)
    return [alerta_salida(alerta) for alerta in db.scalars(consulta).all()]


@router.post("/alertas/{alerta_id}/atender", response_model=AlertaSalida)
def atender_alerta(
    alerta_id: int,
    entrada: AtenderEntrada,
    db: SesionDb,
    usuario: JefeCocina,
    restaurante_id: RestauranteId,
) -> AlertaSalida:
    """Marca quién atendió la alerta y cuándo; no la cierra.

    Es idempotente: si la alerta ya estaba atendida conserva `atendida_en` y
    `atendida_por` (para no empeorar el KPI de tiempo de respuesta) y solo
    actualiza la nota cuando viene en el cuerpo. Solo puede llamarlo el rol
    `jefe_cocina` cuando la autenticación está activa. Una alerta de otro
    restaurante responde 404, igual que una inexistente.
    """
    alerta = db.get(Alerta, alerta_id)
    if alerta is None or alerta.restaurante_id != restaurante_id:
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

    if usuario is None:
        # Sin JWT (AUTH_REQUERIDA=0) se atribuye al primer `jefe_cocina` del
        # restaurante de la petición, que en la demo es el usuario `jefe`.
        usuario = db.scalar(
            select(Usuario)
            .where(
                Usuario.rol == "jefe_cocina",
                Usuario.restaurante_id == restaurante_id,
            )
            .order_by(Usuario.id)
            .limit(1)
        )
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "No hay un usuario con rol jefe_cocina; carga el seed (usuario «jefe») "
                "para poder atender alertas."
            ),
        )

    alerta.atendida_por = usuario.id
    alerta.atendida_en = utcnow()
    if entrada.nota is not None:
        alerta.nota = entrada.nota
    db.commit()

    # El contrato dice que `alerta_cerrada` también se manda cuando la atienden.
    salida = alerta_salida(alerta)
    bus.publicar("alerta_cerrada", salida.model_dump())
    return salida


# Con AUTH_REQUERIDA=0 este endpoint queda abierto; con 1 exige JWT.
@router.get("/kpis", response_model=KpisSalida)
def obtener_kpis(db: SesionDb, restaurante_id: RestauranteId) -> KpisSalida:
    """Calcula los KPIs del restaurante a partir de lecturas, alertas y lotes."""
    return KpisSalida(**calcular_kpis(db, restaurante_id))


# Con AUTH_REQUERIDA=0 este endpoint queda abierto; con 1 exige JWT.
@router.get("/seguridad/alertas", response_model=list[AlertaSeguridadSalida])
def listar_alertas_seguridad(
    db: SesionDb,
    restaurante_id: RestauranteId,
) -> list[AlertaSeguridadSalida]:
    """Devuelve las últimas 20 alertas del detector SIEM.

    El SIEM es de plataforma y todavía no guarda el restaurante de cada
    hallazgo: solo la demo (tenant 1) ve el feed global. Los demás tenants
    reciben una lista vacía hasta que el detector se aísle por restaurante.
    """
    if restaurante_id != RESTAURANTE_DEMO_ID:
        return []
    filas = db.scalars(
        select(AlertaSeguridad)
        .order_by(AlertaSeguridad.ts.desc(), AlertaSeguridad.id.desc())
        .limit(20)
    ).all()
    return [alerta_seguridad_salida(fila) for fila in filas]
