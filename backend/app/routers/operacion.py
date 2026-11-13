"""Alertas operativas, KPIs del dashboard y alertas de seguridad."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Alerta, AlertaSeguridad, Camara, Lectura, Lote, Usuario
from app.db.session import get_db
from app.erp.kpis import (
    merma_en_periodo,
    pct_en_rango,
    promedio_respuesta_min,
    valor_en_riesgo,
)

router = APIRouter(prefix="/api", tags=["operacion"])

SesionDb = Annotated[Session, Depends(get_db)]


class AlertaSalida(BaseModel):
    """Alerta operativa tal como la consume el dashboard."""

    id: int
    camara_id: int
    tipo: str
    abierta_en: str
    cerrada_en: str | None
    atendida_por: int | None
    temperatura_max_c: float | None
    sms_enviados: int


class AtenderEntrada(BaseModel):
    """Cuerpo de `POST /alertas/{id}/atender`; la nota es opcional."""

    nota: str | None = None


class KpisSalida(BaseModel):
    """KPIs del encabezado del dashboard."""

    pct_tiempo_en_rango_24h: float
    alertas_activas: int
    tiempo_respuesta_promedio_min: float
    valor_en_riesgo_mxn: float
    merma_hoy_mxn: float
    merma_mes_mxn: float


class AlertaSeguridadSalida(BaseModel):
    """Hallazgo del detector SIEM."""

    id: int
    regla_id: str
    regla: str
    severidad: str
    ts: str
    ip_origen: str | None
    detalle: dict[str, Any]
    accion: str


def _ahora() -> datetime:
    """Reloj del proceso; las pruebas lo reemplazan para fijar fechas."""
    return datetime.now(UTC)


def _iso(instante: datetime) -> str:
    """Devuelve ISO 8601; si la fecha llegara sin zona, asume UTC."""
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=UTC)
    return instante.isoformat()


def _alerta_salida(alerta: Alerta) -> AlertaSalida:
    return AlertaSalida(
        id=alerta.id,
        camara_id=alerta.camara_id,
        tipo=alerta.tipo,
        abierta_en=_iso(alerta.abierta_en),
        cerrada_en=_iso(alerta.cerrada_en) if alerta.cerrada_en is not None else None,
        atendida_por=alerta.atendida_por,
        temperatura_max_c=(
            float(alerta.temperatura_max_c) if alerta.temperatura_max_c is not None else None
        ),
        sms_enviados=alerta.sms_enviados,
    )


# Auth pendiente (fase posterior): estos endpoints quedan abiertos en local.
@router.get("/alertas", response_model=list[AlertaSalida])
def listar_alertas(
    db: SesionDb,
    activas: bool = False,
) -> list[AlertaSalida]:
    """Lista las alertas de la más reciente a la más antigua; `activas` filtra las abiertas."""
    consulta = select(Alerta).order_by(Alerta.abierta_en.desc(), Alerta.id.desc())
    if activas:
        consulta = consulta.where(Alerta.cerrada_en.is_(None))
    return [_alerta_salida(alerta) for alerta in db.scalars(consulta).all()]


@router.post("/alertas/{alerta_id}/atender", response_model=AlertaSalida)
def atender_alerta(
    alerta_id: int,
    entrada: AtenderEntrada,
    db: SesionDb,
) -> AlertaSalida:
    """Marca quién atendió la alerta y cuándo; no la cierra."""
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")
    if alerta.cerrada_en is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="La alerta ya está cerrada"
        )

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
    return _alerta_salida(alerta)


# Auth pendiente (fase posterior): este endpoint queda abierto en local.
@router.get("/kpis", response_model=KpisSalida)
def obtener_kpis(db: SesionDb) -> KpisSalida:
    """Calcula los KPIs del dashboard a partir de lecturas, alertas y lotes."""
    ahora = _ahora()
    desde = ahora - timedelta(hours=24)

    lecturas = db.execute(
        select(Lectura.temperatura_c, Camara.rango_min_c, Camara.rango_max_c)
        .join(Camara, Camara.id == Lectura.camara_id)
        .where(Lectura.recibida_en >= desde)
    ).all()

    alertas_activas = db.scalar(
        select(func.count()).select_from(Alerta).where(Alerta.cerrada_en.is_(None))
    )

    atendidas = db.execute(
        select(Alerta.abierta_en, Alerta.atendida_en).where(Alerta.atendida_en.is_not(None))
    ).all()

    costos_en_riesgo = db.scalars(
        select(Lote.costo_total_mxn).where(Lote.estado == "en_riesgo")
    ).all()

    mermas = db.execute(
        select(Lote.merma_en, Lote.costo_total_mxn).where(
            Lote.estado == "merma", Lote.merma_en.is_not(None)
        )
    ).all()

    return KpisSalida(
        pct_tiempo_en_rango_24h=pct_en_rango(lecturas),
        alertas_activas=alertas_activas or 0,
        tiempo_respuesta_promedio_min=promedio_respuesta_min(atendidas),
        valor_en_riesgo_mxn=valor_en_riesgo(costos_en_riesgo),
        merma_hoy_mxn=merma_en_periodo(mermas, ahora, "dia"),
        merma_mes_mxn=merma_en_periodo(mermas, ahora, "mes"),
    )


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
    return [
        AlertaSeguridadSalida(
            id=fila.id,
            regla_id=fila.regla_id,
            regla=fila.regla,
            severidad=fila.severidad,
            ts=_iso(fila.ts),
            ip_origen=fila.ip_origen,
            detalle=fila.detalle,
            accion=fila.accion,
        )
        for fila in filas
    ]
