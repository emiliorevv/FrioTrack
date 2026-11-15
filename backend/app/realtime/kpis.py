"""Tarea global que calcula y publica los KPIs de cada restaurante."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.db.models import Camara
from app.db.session import SessionLocal, get_engine
from app.realtime.bus import bus
from app.services.kpis import calcular_kpis

logger = logging.getLogger(__name__)

INTERVALO_KPIS_SEGUNDOS = 30


def calcular_kpis_actuales(restaurante_id: int) -> dict[str, Any]:
    """Calcula los KPIs del tenant en un hilo con su propia sesión, que se cierra al salir."""
    with SessionLocal(bind=get_engine()) as session:
        return calcular_kpis(session, restaurante_id)


def publicar_kpis_de_todos_los_tenants() -> None:
    """Calcula una vez por restaurante con cámaras y publica a sus conexiones.

    Corre en un solo hilo por ciclo: el costo crece con los tenants, no con las
    conexiones SSE abiertas. El bus entrega cada payload solo a las conexiones
    de ese restaurante.
    """
    with SessionLocal(bind=get_engine()) as session:
        tenants = list(session.scalars(select(Camara.restaurante_id).distinct()))
        for restaurante_id in tenants:
            datos = calcular_kpis(session, restaurante_id)
            bus.publicar("kpis", datos, restaurante_id)


async def publicar_kpis_periodicos(intervalo: float = INTERVALO_KPIS_SEGUNDOS) -> None:
    """Una sola tarea para toda la app: un cálculo por tenant cada `intervalo`.

    Se salta el ciclo si no hay conexiones SSE: sin suscriptores nadie recibe
    el evento y las queries serían trabajo tirado. Las conexiones nuevas
    calculan sus KPIs al conectar.
    """
    while True:
        await asyncio.sleep(intervalo)
        if not bus.hay_suscriptores():
            continue
        try:
            await run_in_threadpool(publicar_kpis_de_todos_los_tenants)
        except Exception:  # la API sigue viva aunque la base falle un momento
            logger.exception("No se pudieron calcular los KPIs del stream")
