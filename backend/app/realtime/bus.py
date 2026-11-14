"""Bus de eventos en memoria para empujar cambios a las conexiones SSE.

Una sola instancia de la API (ADR-0004): cada conexión de `/api/stream` se
suscribe con su propia `asyncio.Queue` y la ingesta publica sin bloquearse.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

TAMANO_COLA = 100
# El stream cierra la conexión al recibirlo para que `EventSource` reconecte y
# recargue el estado completo por REST.
EVENTO_CERRAR = "__cerrar__"
# Transiciones de estado: si se pierden, el dashboard queda desincronizado.
EVENTOS_DE_ESTADO = frozenset({"alerta_abierta", "alerta_cerrada", "lote_actualizado", "kpis"})
# La notificación tampoco se puede perder: con la cola llena se le hace espacio.
EVENTOS_IMPORTANTES = EVENTOS_DE_ESTADO | {"notificacion"}
# Muestras que sí se pueden tirar: la próxima lectura o el próximo KPI las repone.
EVENTOS_DESCARTABLES = frozenset({"lectura", "kpis"})

Evento = tuple[str, dict[str, Any]]
ColaEventos = asyncio.Queue[Evento]


def _hacer_espacio(cola: ColaEventos) -> bool:
    """Descarta el evento descartable más antiguo y conserva el orden del resto.

    Se llama solo con la cola llena y desde el loop de la conexión, así que
    nadie más la toca mientras se drena.
    """
    pendientes: list[Evento] = []
    descartado = False
    while not cola.empty():
        evento = cola.get_nowait()
        if not descartado and evento[0] in EVENTOS_DESCARTABLES:
            descartado = True
            continue
        pendientes.append(evento)
    for evento in pendientes:
        cola.put_nowait(evento)
    return descartado


class EventBus:
    """Reparte eventos a las colas suscritas sin bloquear al publicador."""

    def __init__(self) -> None:
        self._suscriptores: dict[ColaEventos, asyncio.AbstractEventLoop] = {}

    def suscribir(self) -> ColaEventos:
        """Crea la cola de una conexión y la asocia al loop donde vive."""
        loop = asyncio.get_running_loop()
        cola: ColaEventos = asyncio.Queue(maxsize=TAMANO_COLA)
        self._suscriptores[cola] = loop
        return cola

    def desuscribir(self, cola: ColaEventos) -> None:
        """Deja de entregar eventos a la cola (conexión cerrada)."""
        self._suscriptores.pop(cola, None)

    def hay_suscriptores(self) -> bool:
        """Indica si vale la pena calcular eventos que nadie va a recibir."""
        return bool(self._suscriptores)

    def publicar(self, evento: str, data: dict[str, Any]) -> None:
        """Encola el evento en cada conexión, en el loop de esa conexión.

        Se puede llamar desde cualquier hilo: `call_soon_threadsafe` devuelve el
        reparto al loop donde vive cada cola (no todas las conexiones comparten
        loop, por ejemplo entre TestClient o un segundo loop de pruebas).
        """
        for cola, loop in list(self._suscriptores.items()):
            if loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(self._entregar, cola, evento, data)
            except RuntimeError:
                # El loop se cerró entre la comprobación y la llamada.
                logger.debug("Evento %s descartado: el loop ya no está disponible", evento)

    def _entregar(self, cola: ColaEventos, evento: str, data: dict[str, Any]) -> None:
        """Encola el evento; con la cola llena, protege lo que no se puede perder."""
        if not cola.full():
            cola.put_nowait((evento, data))
            return
        if evento not in EVENTOS_IMPORTANTES:
            # Las lecturas son muestras: perder una no desincroniza el dashboard.
            logger.debug("Cola SSE llena: se descarta el evento %s", evento)
            return
        if evento in EVENTOS_DE_ESTADO:
            # Un evento de estado perdido deja al cliente desincronizado para
            # siempre (una alerta que nunca aparece, un lote que nunca pasa a
            # merma). Se vacía la cola y se pide reconectar para recargar por REST.
            logger.warning("Cola SSE llena: se pide reconectar para no perder %s", evento)
            self._pedir_reconexion(cola)
            return
        # `notificacion`: se sacrifica la muestra más antigua y la notificación
        # se entrega. Si no hay nada descartable, se pide reconectar.
        if _hacer_espacio(cola):
            cola.put_nowait((evento, data))
            return
        logger.warning(
            "Cola SSE llena sin eventos descartables: se pide reconectar para no perder %s",
            evento,
        )
        self._pedir_reconexion(cola)

    @staticmethod
    def _pedir_reconexion(cola: ColaEventos) -> None:
        """Deja solo el cierre para que el cliente recargue el estado por REST."""
        while not cola.empty():
            cola.get_nowait()
        cola.put_nowait((EVENTO_CERRAR, {}))


bus = EventBus()
