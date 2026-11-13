"""Esquemas de salida compartidos por los endpoints y los eventos SSE.

El REST y el stream usan los mismos modelos para que los payloads no se
separen cuando cambie un campo de la alerta o del lote.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.db.models import Alerta, AlertaSeguridad, Lote
from app.schemas.utils import iso


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


def alerta_salida(alerta: Alerta) -> AlertaSalida:
    """Objeto de alerta del contrato, sin atributos ORM."""
    return AlertaSalida(
        id=alerta.id,
        camara_id=alerta.camara_id,
        tipo=alerta.tipo,
        abierta_en=iso(alerta.abierta_en),
        cerrada_en=iso(alerta.cerrada_en),
        atendida_por=alerta.atendida_por,
        temperatura_max_c=(
            float(alerta.temperatura_max_c) if alerta.temperatura_max_c is not None else None
        ),
        sms_enviados=alerta.sms_enviados,
    )


class LoteSalida(BaseModel):
    """Lote de inventario tal como lo consume el dashboard."""

    id: int
    producto: str
    camara_id: int
    cantidad: float
    unidad: str
    costo_total_mxn: float
    caducidad: str | None
    estado: str


def lote_salida(lote: Lote) -> LoteSalida:
    """Objeto de lote del contrato, sin atributos ORM."""
    return LoteSalida(
        id=lote.id,
        producto=lote.producto,
        camara_id=lote.camara_id,
        cantidad=float(lote.cantidad),
        unidad=lote.unidad,
        costo_total_mxn=float(lote.costo_total_mxn),
        caducidad=iso(lote.caducidad),
        estado=lote.estado,
    )


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


def alerta_seguridad_salida(fila: AlertaSeguridad) -> AlertaSeguridadSalida:
    """Objeto de alerta de seguridad del contrato, sin atributos ORM."""
    return AlertaSeguridadSalida(
        id=fila.id,
        regla_id=fila.regla_id,
        regla=fila.regla,
        severidad=fila.severidad,
        ts=iso(fila.ts),
        ip_origen=fila.ip_origen,
        detalle=fila.detalle,
        accion=fila.accion,
    )
