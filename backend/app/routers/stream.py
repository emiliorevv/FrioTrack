"""GET /api/stream: eventos del dashboard por Server-Sent Events (SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.db.session import SessionLocal, get_engine
from app.realtime.bus import ColaEventos, bus
from app.services.kpis import calcular_kpis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tiempo-real"])

INTERVALO_KPIS_SEGUNDOS = 30
ESPERA_EVENTO_SEGUNDOS = 15


def _calcular_kpis() -> dict[str, Any]:
    """Calcula los KPIs en un hilo con su propia sesión, que se cierra al salir."""
    with SessionLocal(bind=get_engine()) as session:
        return calcular_kpis(session)


async def _kpis_periodicos(cola: ColaEventos) -> None:
    """Cada 30 s encola un evento `kpis` con el mismo cuerpo que `GET /kpis`."""
    while True:
        await asyncio.sleep(INTERVALO_KPIS_SEGUNDOS)
        try:
            datos = await run_in_threadpool(_calcular_kpis)
        except Exception:  # la conexión sigue viva aunque la base falle un momento
            logger.exception("No se pudieron calcular los KPIs del stream")
            continue
        await cola.put(("kpis", datos))


def _sse(evento: str, datos: dict[str, Any]) -> str:
    """Formatea un evento SSE: una línea `event:` y una `data:` en JSON."""
    cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    return f"event: {evento}\ndata: {cuerpo}\n\n"


async def _eventos(request: Request) -> AsyncIterator[str]:
    """Genera el cuerpo SSE de una conexión hasta que el cliente se desconecta."""
    cola = bus.suscribir()
    tarea = asyncio.create_task(_kpis_periodicos(cola))
    try:
        yield "retry: 3000\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                evento, datos = await asyncio.wait_for(
                    cola.get(), timeout=ESPERA_EVENTO_SEGUNDOS
                )
            except TimeoutError:
                continue
            yield _sse(evento, datos)
    finally:
        tarea.cancel()
        with suppress(asyncio.CancelledError):
            await tarea
        bus.desuscribir(cola)


@router.get("/stream")
async def stream(request: Request, token: str | None = None) -> StreamingResponse:
    """Mantiene abierta la conexión SSE del dashboard.

    `EventSource` del navegador no deja mandar headers, así que el contrato
    manda el token en la URL. JWT pendiente (fase posterior): se acepta pero
    todavía no se valida.
    """
    return StreamingResponse(
        _eventos(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
