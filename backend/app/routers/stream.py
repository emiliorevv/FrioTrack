"""GET /api/stream: eventos del dashboard por Server-Sent Events (SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.auth import RestauranteIdStream, get_current_user_stream
from app.db.models import Camara
from app.db.session import SessionLocal, get_engine
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


# El cupo evita que cualquiera tumbe Postgres abriendo conexiones; con
# AUTH_REQUERIDA=1 además hay que presentar un JWT válido.
limite_conexiones = LimiteConexiones(MAX_CONEXIONES_STREAM)


def _sse(evento: str, datos: dict[str, Any]) -> str:
    """Formatea un evento SSE: una línea `event:` y una `data:` en JSON."""
    cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    return f"event: {evento}\ndata: {cuerpo}\n\n"


def _ids_de_camaras(restaurante_id: int) -> frozenset[int]:
    """IDs de las cámaras del restaurante, con una sesión corta propia."""
    with SessionLocal(bind=get_engine()) as session:
        return frozenset(
            session.scalars(
                select(Camara.id).where(Camara.restaurante_id == restaurante_id)
            )
        )


async def _camaras_permitidas(restaurante_id: int) -> frozenset[int]:
    """Carga los IDs permitidos; si la base falla, no se filtra nada hacia afuera."""
    try:
        return await run_in_threadpool(_ids_de_camaras, restaurante_id)
    except Exception:
        logger.exception(
            "No se pudieron cargar las cámaras del restaurante %s; "
            "se descartan los eventos hasta el próximo refresco",
            restaurante_id,
        )
        return frozenset()


async def _eventos(request: Request, restaurante_id: int) -> AsyncIterator[str]:
    """Genera el cuerpo SSE de una conexión hasta que el cliente se desconecta.

    Solo se reenvían los eventos de cámaras del restaurante de la conexión. La
    lista se carga al conectar y se refresca en cada `kpis` (cada ~30 s) para
    incluir cámaras nuevas sin reconectar.
    """
    cola = bus.suscribir()
    try:
        permitidas = await _camaras_permitidas(restaurante_id)
        yield "retry: 3000\n\n"
        # El dashboard no espera los 30 s del ciclo global para ver KPIs; la
        # tarea global se encarga de los siguientes.
        try:
            yield _sse(
                "kpis",
                await run_in_threadpool(calcular_kpis_actuales, restaurante_id),
            )
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
            if evento == "kpis":
                # La tarea periódica solo manda la señal: cada conexión recalcula
                # los KPIs de su restaurante y refresca sus cámaras permitidas.
                permitidas = await _camaras_permitidas(restaurante_id)
                try:
                    yield _sse(
                        "kpis",
                        await run_in_threadpool(calcular_kpis_actuales, restaurante_id),
                    )
                except Exception:
                    logger.exception("No se pudieron recalcular los KPIs del stream")
                continue
            camara_id = datos.get("camara_id")
            if camara_id is not None and camara_id not in permitidas:
                # Evento de otro restaurante: ni siquiera se menciona.
                continue
            yield _sse(evento, datos)
    finally:
        bus.desuscribir(cola)
        limite_conexiones.liberar()


@router.get("/stream", dependencies=[Depends(get_current_user_stream)])
async def stream(
    request: Request,
    restaurante_id: RestauranteIdStream,
    token: str | None = None,
) -> StreamingResponse:
    """Mantiene abierta la conexión SSE del dashboard.

    `EventSource` del navegador no deja mandar headers, así que el contrato
    manda el token en la URL. Cuando `AUTH_REQUERIDA=1`, sin `?token=<jwt>`
    válido la conexión responde 401; con la bandera apagada se acepta sin token
    y se transmite el restaurante demo.
    """
    limite_conexiones.adquirir()
    return StreamingResponse(
        _eventos(request, restaurante_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
