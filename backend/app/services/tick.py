"""Tick del cron: lecturas normales para las cámaras sin datos frescos."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import utcnow
from app.db.models import Camara, Lectura
from app.schemas.telemetria import TelemetriaIn
from app.services.telemetria import procesar_lectura
from simulator.escenarios import (
    HUMEDAD_POR_DEFECTO,
    azar_aleatorio,
    siguiente_lectura,
)

logger = logging.getLogger(__name__)

# Sensor ficticio con el que el cron firma sus lecturas; no existe en `sensores`.
SENSOR_CRON = "SIM-CRON"
# Tiempo real del servidor, no escalado: si el simulador mandó algo hace menos de
# esto, el tick no lo pisa (una falla provocada en la demo manda).
VENTANA_LECTURA_REAL = timedelta(minutes=2)
# Dedupe de ticks solapados (por ejemplo, si Render tarda en despertar).
VENTANA_TICK = timedelta(seconds=30)


def _ids_de_camaras(session: Session) -> list[int]:
    """IDs de todas las cámaras, ordenados; cada una se bloquea al procesarla."""
    return list(session.scalars(select(Camara.id).order_by(Camara.id)))


def _hay_lectura_reciente(
    session: Session, camara_id: int, desde: datetime, *, solo_cron: bool
) -> bool:
    """Si la cámara tiene alguna lectura desde `desde` (del cron o de un sensor).

    Usa el índice existente `(camara_id, recibida_en DESC)`.
    """
    condicion = (
        Lectura.sensor_id == SENSOR_CRON if solo_cron else Lectura.sensor_id != SENSOR_CRON
    )
    return (
        session.scalar(
            select(Lectura.id)
            .where(
                Lectura.camara_id == camara_id,
                Lectura.recibida_en >= desde,
                condicion,
            )
            .limit(1)
        )
        is not None
    )


def ejecutar_tick(session: Session) -> tuple[int, list[int]]:
    """Genera una lectura normal por cámara sin lectura real reciente.

    Solo genera en modo demo (`ESCALA_TIEMPO > 1`); en producción apenas
    mantiene despierta la API. Regresa `(cantidad_generada, saltadas)`.
    """
    settings = get_settings()
    if settings.escala_tiempo <= 1:
        logger.info(
            "Tick omitido: ESCALA_TIEMPO=%s (solo genera en modo demo)",
            settings.escala_tiempo,
        )
        return 0, []

    ahora = utcnow()
    desde_real = ahora - VENTANA_LECTURA_REAL
    desde_tick = ahora - VENTANA_TICK

    generadas = 0
    saltadas: list[int] = []
    for camara_id in _ids_de_camaras(session):
        # El lock serializa contra `procesar_telemetria`: así una lectura real
        # que llega a mitad del tick no se pierde. Se pide por id (no por
        # entidad) para que el lock sí se emita.
        camara = session.get(Camara, camara_id, with_for_update=True)
        if camara is None:
            continue

        if _hay_lectura_reciente(
            session, camara_id, desde_real, solo_cron=False
        ) or _hay_lectura_reciente(session, camara_id, desde_tick, solo_cron=True):
            saltadas.append(camara_id)
            continue

        try:
            # El escenario normal ignora la lectura anterior: no hace falta consultarla.
            simulada = siguiente_lectura(
                "normal",
                float(camara.rango_min_c),
                float(camara.rango_max_c),
                None,
                azar_aleatorio(),
            )
            procesar_lectura(
                session,
                TelemetriaIn(
                    sensor_id=SENSOR_CRON,
                    camara_id=camara.id,
                    ts=ahora,
                    temperatura_c=simulada.temperatura_c,
                    humedad_pct=HUMEDAD_POR_DEFECTO,
                    puerta_abierta=simulada.puerta_abierta,
                ),
                camara,
            )
        except Exception:
            session.rollback()
            logger.exception(
                "El tick no pudo procesar la cámara %s; se continúa con la siguiente.",
                camara_id,
            )
            continue

        generadas += 1

    return generadas, saltadas
