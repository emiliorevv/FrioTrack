"""Infraestructura de tiempo real: bus en memoria que alimenta `GET /api/stream`."""

from app.realtime.bus import ColaEventos, EventBus, bus

__all__ = ["ColaEventos", "EventBus", "bus"]
