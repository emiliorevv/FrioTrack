"""Canal de notificaciones de alertas y mermas.

En la demo el canal es **simulado**: no sale nada a la red, solo se escribe en
el log y se publica el evento SSE `notificacion` para que el dashboard la
muestre. `Notificador` es la interfaz que después puede implementar Twilio
(ADR-0008) sin tocar la ingesta.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.config import get_settings
from app.db.models import Alerta, Camara, Lote
from app.erp.procesador import TIPO_ALERTA_PUERTA, TIPO_ALERTA_TEMPERATURA
from app.erp.reglas import asegurar_utc
from app.realtime.bus import bus
from app.schemas.utils import iso

logger = logging.getLogger(__name__)

CANAL_SIMULADO = "simulado"

# Valores del campo `tipo` del evento SSE `notificacion`.
NOTIFICACION_TEMPERATURA = "alerta_temperatura"
NOTIFICACION_PUERTA = "alerta_puerta"
NOTIFICACION_MERMA = "merma"


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


def _monto(lotes: Sequence[Lote]) -> int:
    """Costo total en pesos, redondeado y sin decimales."""
    total = sum((lote.costo_total_mxn for lote in lotes), start=Decimal("0"))
    return int(round(total))


def _pesos(monto: int) -> str:
    """Formato del contrato: `$4,850`."""
    return f"${monto:,}"


def _minutos(desde: datetime | None, ahora: datetime, escala: float) -> int:
    """Minutos de demo transcurridos desde `desde`; sin fecha, reporta 1."""
    if desde is None:
        return 1
    segundos = (asegurar_utc(ahora) - asegurar_utc(desde)).total_seconds()
    return max(1, round(segundos * escala / 60))


def _mensaje_temperatura(
    camara: str, temperatura: float | Decimal, minutos: int, monto: int
) -> str:
    """Mensaje de una alerta de temperatura, con el dinero solo si hay riesgo."""
    base = f"FríoTrack: Cámara {camara} a {temperatura:.1f} °C hace {minutos} min."
    return f"{base} {_pesos(monto)} en riesgo." if monto else base


def _mensaje_puerta(camara: str, minutos: int, monto: int) -> str:
    """Mensaje de una alerta de puerta, con el dinero solo si hay riesgo."""
    base = f"FríoTrack: Puerta abierta en Cámara {camara} hace {minutos} min."
    return f"{base} {_pesos(monto)} en riesgo." if monto else base


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


def notificar_cambios(
    camara: Camara,
    alertas_nuevas: Sequence[Alerta],
    lotes: Sequence[Lote],
    lotes_a_merma: Sequence[Lote],
    ahora: datetime,
    escala: float,
    temperatura: float,
) -> None:
    """Notifica las alertas recién abiertas y los lotes que pasaron a merma.

    Se llama después del commit y solo por transiciones: al abrir una alerta o
    al marcarse la merma, nunca una vez por lectura.
    """
    url = get_settings().dashboard_url
    monto_en_riesgo = _monto([lote for lote in lotes if lote.estado == "en_riesgo"])

    for alerta in alertas_nuevas:
        if alerta.tipo == TIPO_ALERTA_TEMPERATURA:
            grados = (
                alerta.temperatura_max_c
                if alerta.temperatura_max_c is not None
                else temperatura
            )
            tipo = NOTIFICACION_TEMPERATURA
            mensaje = _mensaje_temperatura(
                camara.nombre,
                grados,
                _minutos(camara.fuera_de_rango_desde, ahora, escala),
                monto_en_riesgo,
            )
        elif alerta.tipo == TIPO_ALERTA_PUERTA:
            tipo = NOTIFICACION_PUERTA
            mensaje = _mensaje_puerta(
                camara.nombre,
                _minutos(camara.puerta_abierta_desde, ahora, escala),
                monto_en_riesgo,
            )
        else:
            continue
        _enviar(
            Notificacion(
                tipo=tipo,
                camara_id=camara.id,
                mensaje=mensaje,
                ts=ahora,
                url=url,
            )
        )

    if lotes_a_merma:
        _enviar(
            Notificacion(
                tipo=NOTIFICACION_MERMA,
                camara_id=camara.id,
                mensaje=_mensaje_merma(
                    camara.nombre, len(lotes_a_merma), _monto(lotes_a_merma)
                ),
                ts=ahora,
                url=url,
            )
        )
