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

Evento = tuple[str, dict[str, Any]]
ColaEventos = asyncio.Queue[Evento]


class EventBus:
    """Reparte eventos a las colas suscritas sin bloquear al publicador."""

    def __init__(self) -> None:
        self._suscriptores: set[ColaEventos] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def suscribir(self) -> ColaEventos:
        """Crea la cola de una conexión y recuerda el loop donde vive.

        El loop se guarda en la primera suscripción para poder publicar desde
        los endpoints sync, que FastAPI ejecuta en el threadpool.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Suscripción sin loop (uso sync): se publicará cuando exista uno.
            loop = None
        if loop is not None:
            self._loop = loop

        cola: ColaEventos = asyncio.Queue(maxsize=TAMANO_COLA)
        self._suscriptores.add(cola)
        return cola

    def desuscribir(self, cola: ColaEventos) -> None:
        """Deja de entregar eventos a la cola (conexión cerrada)."""
        self._suscriptores.discard(cola)

    def publicar(self, evento: str, data: dict[str, Any]) -> None:
        """Encola el evento en todas las conexiones; nunca bloquea ni falla.

        Si la publicación viene de un endpoint sync, se corre en otro hilo:
        `call_soon_threadsafe` devuelve el reparto al loop de las conexiones.
        """
        loop = self._loop
        if not self._suscriptores or loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._repartir, evento, data)
        except RuntimeError:
            # El loop se cerró entre la comprobación y la llamada.
            logger.debug("Evento %s descartado: el loop ya no está disponible", evento)

    def _repartir(self, evento: str, data: dict[str, Any]) -> None:
        """Copia el evento a cada cola; si una está llena, lo descarta."""
        for cola in list(self._suscriptores):
            try:
                cola.put_nowait((evento, data))
            except asyncio.QueueFull:
                logger.debug("Cola SSE llena: se descarta el evento %s", evento)


bus = EventBus()
