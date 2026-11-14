"""Canal de notificaciones de alertas y mermas.

En la demo el canal es **simulado**: no sale nada a la red, solo se escribe en
el log y se publica el evento SSE `notificacion` para que el dashboard la
muestre. `Notificador` es la interfaz que después puede implementar Twilio
(ADR-0008) sin tocar la ingesta.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from app.config import Settings
from app.db.models import Alerta, Camara, Lote
from app.erp.procesador import TIPO_ALERTA_PUERTA, TIPO_ALERTA_TEMPERATURA
from app.erp.reglas import calcular_valor_en_riesgo, minutos_demo
from app.realtime.bus import bus
from app.schemas.utils import iso

logger = logging.getLogger(__name__)

CANAL_SIMULADO = "simulado"

# Valores del campo `tipo` del evento SSE `notificacion`.
NOTIFICACION_TEMPERATURA = "alerta_temperatura"
NOTIFICACION_PUERTA = "alerta_puerta"
NOTIFICACION_MERMA = "merma"

# El envío va en segundo plano (ADR-0008): la ingesta no espera al canal ni se
# cae si este falla. Un solo hilo conserva el orden de agendado (temperatura
# antes que merma); el volumen de la demo es mínimo.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notificaciones")
_pendientes = 0
_lock_pendientes = threading.Lock()


@dataclass(frozen=True)
class Notificacion:
    """Mensaje listo para entregar por cualquier canal."""

    tipo: str
    camara_id: int
    mensaje: str
    ts: datetime
    canal: str = CANAL_SIMULADO
    url: str = ""


class Notificador(Protocol):
    """Interfaz mínima de un canal de notificaciones."""

    def enviar(self, notificacion: Notificacion) -> None:
        """Entrega la notificación; puede fallar sin tumbar a quien la llama."""


class NotificadorSimulado:
    """Canal de la demo: log del servidor más el evento SSE del dashboard."""

    def enviar(self, notificacion: Notificacion) -> None:
        logger.info(
            "Notificación simulada (%s): %s",
            notificacion.tipo,
            notificacion.mensaje,
        )
        bus.publicar(
            "notificacion",
            {
                "canal": notificacion.canal,
                "tipo": notificacion.tipo,
                "camara_id": notificacion.camara_id,
                "mensaje": notificacion.mensaje,
                "ts": iso(notificacion.ts),
                "url": notificacion.url,
            },
        )


# Punto único de cambio: para producción basta con asignar aquí un Notificador
# que hable con Twilio.
notificador: Notificador = NotificadorSimulado()


def _a_pesos(total: Decimal) -> int:
    """Pesos enteros con redondeo half-up (el dinero no se trunca)."""
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _pesos(monto: int) -> str:
    """Formato del contrato: `$4,850`."""
    return f"${monto:,}"


def _mensaje_temperatura(
    camara: str, temperatura: float | Decimal, minutos: int, monto: int
) -> str:
    """Mensaje de una alerta de temperatura, con el dinero solo si hay riesgo."""
    base = f"FríoTrack: Cámara {camara} a {temperatura:.1f} °C hace {minutos} min."
    return f"{base} {_pesos(monto)} en riesgo." if monto else base


def _mensaje_puerta(camara: str, minutos: int) -> str:
    """Mensaje de una alerta de puerta; no incluye dinero en riesgo."""
    return f"FríoTrack: Puerta abierta en Cámara {camara} hace {minutos} min."


def _mensaje_merma(camara: str, cantidad: int, monto: int) -> str:
    """Mensaje de los lotes que pasaron a merma (singular o plural)."""
    if cantidad == 1:
        texto = "1 lote pasó a merma"
    else:
        texto = f"{cantidad} lotes pasaron a merma"
    detalle = f" ({_pesos(monto)})" if monto else ""
    return f"FríoTrack: Cámara {camara}: {texto}{detalle}."


def _enviar(notificacion: Notificacion) -> None:
    """Entrega una notificación; un canal caído no debe romper la ingesta."""
    try:
        notificador.enviar(notificacion)
    except Exception:
        logger.exception(
            "No se pudo enviar la notificación %s de la cámara %s",
            notificacion.tipo,
            notificacion.camara_id,
        )


def _programar(notificacion: Notificacion) -> None:
    """Agenda el envío y cuenta los que todavía no terminan."""
    global _pendientes
    with _lock_pendientes:
        _pendientes += 1
    _executor.submit(_ejecutar, notificacion)


def _ejecutar(notificacion: Notificacion) -> None:
    """Envía y descuenta el pendiente aunque el canal falle."""
    global _pendientes
    try:
        _enviar(notificacion)
    finally:
        with _lock_pendientes:
            _pendientes -= 1


def cerrar_notificaciones() -> None:
    """Cierra el executor al apagar la app sin esperar los envíos pendientes."""
    with _lock_pendientes:
        pendientes = _pendientes
    logger.info("Cerrando notificaciones: %s pendientes", pendientes)
    _executor.shutdown(wait=False, cancel_futures=True)


def notificar_cambios(
    camara: Camara,
    alertas_nuevas: Sequence[Alerta],
    lotes: Sequence[Lote],
    lotes_a_merma: Sequence[Lote],
    ahora: datetime,
    settings: Settings,
) -> None:
    """Notifica las alertas recién abiertas y los lotes que pasaron a merma.

    Se llama después del commit y solo por transiciones: al abrir una alerta o
    al marcarse la merma, nunca una vez por lectura. Los envíos se agendan en
    segundo plano, así que la función no espera al canal.
    """
    monto_en_riesgo = _a_pesos(calcular_valor_en_riesgo(lotes))
    monto_merma = _a_pesos(
        sum((lote.costo_total_mxn for lote in lotes_a_merma), start=Decimal("0"))
    )
    url = settings.dashboard_url

    for alerta in alertas_nuevas:
        if alerta.tipo == TIPO_ALERTA_TEMPERATURA:
            if alerta.temperatura_max_c is None:
                logger.error(
                    "Alerta %s sin temperatura_max_c; no se notifica", alerta.id
                )
                continue
            tipo = NOTIFICACION_TEMPERATURA
            mensaje = _mensaje_temperatura(
                camara.nombre,
                alerta.temperatura_max_c,
                minutos_demo(
                    camara.fuera_de_rango_desde, ahora, settings.escala_tiempo
                ),
                monto_en_riesgo + monto_merma,
            )
        elif alerta.tipo == TIPO_ALERTA_PUERTA:
            tipo = NOTIFICACION_PUERTA
            mensaje = _mensaje_puerta(
                camara.nombre,
                minutos_demo(
                    camara.puerta_abierta_desde, ahora, settings.escala_tiempo
                ),
            )
        else:
            continue
        _programar(
            Notificacion(
                tipo=tipo,
                camara_id=camara.id,
                mensaje=mensaje,
                ts=ahora,
                url=url,
            )
        )

    if lotes_a_merma:
        _programar(
            Notificacion(
                tipo=NOTIFICACION_MERMA,
                camara_id=camara.id,
                mensaje=_mensaje_merma(camara.nombre, len(lotes_a_merma), monto_merma),
                ts=ahora,
                url=url,
            )
        )
