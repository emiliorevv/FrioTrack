"""GET /api/stream: eventos del dashboard por Server-Sent Events (SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.realtime.bus import EVENTO_CERRAR, bus
from app.realtime.kpis import calcular_kpis_actuales

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tiempo-real"])

MAX_CONEXIONES_STREAM = 50
ESPERA_EVENTO_SEGUNDOS = 15
PING = ": ping\n\n"


class LimiteConexiones:
    """Cupo de conexiones SSE simultáneas; al llenarse responde 503."""

    def __init__(self, maximo: int) -> None:
        self._maximo = maximo
        self._activas = 0

    def adquirir(self) -> None:
        if self._activas >= self._maximo:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Demasiadas conexiones SSE abiertas; reintenta en unos segundos.",
            )
        self._activas += 1

    def liberar(self) -> None:
        if self._activas > 0:
            self._activas -= 1


# Sin JWT todavía: el cupo evita que cualquiera tumbe Postgres abriendo conexiones.
limite_conexiones = LimiteConexiones(MAX_CONEXIONES_STREAM)


def _sse(evento: str, datos: dict[str, Any]) -> str:
    """Formatea un evento SSE: una línea `event:` y una `data:` en JSON."""
    cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    return f"event: {evento}\ndata: {cuerpo}\n\n"


async def _eventos(request: Request) -> AsyncIterator[str]:
    """Genera el cuerpo SSE de una conexión hasta que el cliente se desconecta."""
    cola = bus.suscribir()
    try:
        yield "retry: 3000\n\n"
        # El dashboard no espera los 30 s del ciclo global para ver KPIs; la
        # tarea global se encarga de los siguientes.
        try:
            yield _sse("kpis", await run_in_threadpool(calcular_kpis_actuales))
        except Exception:  # la conexión sigue viva aunque la base falle un momento
            logger.exception("No se pudieron calcular los KPIs iniciales del stream")

        while True:
            if await request.is_disconnected():
                break
            try:
                evento, datos = await asyncio.wait_for(
                    cola.get(), timeout=ESPERA_EVENTO_SEGUNDOS
                )
            except TimeoutError:
                # Sin tráfico, un comentario SSE evita que nginx/Render corten
                # la conexión por inactividad.
                yield PING
                continue
            if evento == EVENTO_CERRAR:
                # El bus pide reconectar: `EventSource` recarga el estado por REST.
                break
            yield _sse(evento, datos)
    finally:
        bus.desuscribir(cola)
        limite_conexiones.liberar()


@router.get("/stream")
async def stream(request: Request, token: str | None = None) -> StreamingResponse:
    """Mantiene abierta la conexión SSE del dashboard.

    `EventSource` del navegador no deja mandar headers, así que el contrato
    manda el token en la URL. JWT pendiente (fase posterior): se acepta pero
    todavía no se valida; mientras tanto hay un cupo de conexiones simultáneas.
    """
    limite_conexiones.adquirir()
    return StreamingResponse(
        _eventos(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
