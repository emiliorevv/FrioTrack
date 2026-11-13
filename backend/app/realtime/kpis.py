"""Tarea global que publica los KPIs por el bus mientras haya suscriptores."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi.concurrency import run_in_threadpool

from app.db.session import SessionLocal, get_engine
from app.realtime.bus import bus
from app.services.kpis import calcular_kpis

logger = logging.getLogger(__name__)

INTERVALO_KPIS_SEGUNDOS = 30


def calcular_kpis_actuales() -> dict[str, Any]:
    """Calcula los KPIs en un hilo con su propia sesión, que se cierra al salir."""
    with SessionLocal(bind=get_engine()) as session:
        return calcular_kpis(session)


async def publicar_kpis_periodicos(intervalo: float = INTERVALO_KPIS_SEGUNDOS) -> None:
    """Una sola tarea para toda la app: calcula una vez y reparte por el bus.

    Se salta el cálculo si no hay conexiones SSE: sin suscriptores nadie recibe
    el evento y las cinco queries serían trabajo tirado.
    """
    while True:
        await asyncio.sleep(intervalo)
        if not bus.hay_suscriptores():
            continue
        try:
            datos = await run_in_threadpool(calcular_kpis_actuales)
        except Exception:  # la API sigue viva aunque la base falle un momento
            logger.exception("No se pudieron calcular los KPIs del stream")
            continue
        bus.publicar("kpis", datos)
