"""Tarea global que avisa a las conexiones SSE cuándo recalcular sus KPIs."""

from __future__ import annotations

import asyncio
from typing import Any

from app.db.session import SessionLocal, get_engine
from app.realtime.bus import bus
from app.services.kpis import calcular_kpis

INTERVALO_KPIS_SEGUNDOS = 30


def calcular_kpis_actuales(restaurante_id: int) -> dict[str, Any]:
    """Calcula los KPIs del tenant en un hilo con su propia sesión, que se cierra al salir."""
    with SessionLocal(bind=get_engine()) as session:
        return calcular_kpis(session, restaurante_id)


async def publicar_kpis_periodicos(intervalo: float = INTERVALO_KPIS_SEGUNDOS) -> None:
    """Una sola tarea para toda la app que publica la señal `kpis`.

    Los KPIs son distintos por restaurante, así que el bus no puede repartir una
    foto global: cada conexión de `/api/stream` recalcula los suyos (y refresca
    su lista de cámaras) al recibir el evento. Sin suscriptores no se publica
    nada; las conexiones nuevas calculan sus KPIs al conectar.
    """
    while True:
        await asyncio.sleep(intervalo)
        if bus.hay_suscriptores():
            bus.publicar("kpis", {})
