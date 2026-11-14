"""Tick del cron: lecturas normales para las cámaras sin datos frescos."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Camara, Lectura
from app.schemas.telemetria import TelemetriaIn
from app.services.telemetria import procesar_lectura
from simulator.escenarios import azar_aleatorio, siguiente_lectura

# Sensor ficticio con el que el cron firma sus lecturas; no existe en `sensores`.
SENSOR_CRON = "SIM-CRON"
# Tiempo real del servidor, no escalado: si el simulador mandó algo hace menos de
# esto, el tick no lo pisa (una falla provocada en la demo manda).
VENTANA_LECTURA_REAL = timedelta(minutes=2)
# Misma humedad que usa el simulador.
HUMEDAD_DEMO = 80.0


def ejecutar_tick(session: Session) -> tuple[int, list[int]]:
    """Genera una lectura normal por cámara sin lectura real reciente.

    Regresa `(cantidad_generada, saltadas)`, donde `saltadas` son las cámaras
    que ya tenían una lectura del simulador dentro de `VENTANA_LECTURA_REAL`.
    """
    ahora = utcnow()
    desde = ahora - VENTANA_LECTURA_REAL

    camaras = list(session.scalars(select(Camara).order_by(Camara.id)))
    # La ventana usa `recibida_en` (hora del servidor), no el `ts` del sensor.
    con_lectura_real = set(
        session.scalars(
            select(Lectura.camara_id)
            .where(
                Lectura.recibida_en >= desde,
                Lectura.sensor_id != SENSOR_CRON,
            )
            .distinct()
        )
    )

    generadas = 0
    saltadas: list[int] = []
    for camara in camaras:
        if camara.id in con_lectura_real:
            saltadas.append(camara.id)
            continue

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
                humedad_pct=HUMEDAD_DEMO,
                puerta_abierta=simulada.puerta_abierta,
            ),
        )
        generadas += 1

    return generadas, saltadas
