"""Aplicación FastAPI de FríoTrack."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.middleware.acceso import AccesoLogMiddleware
from app.realtime.kpis import publicar_kpis_periodicos
from app.routers.camaras import router as camaras_router
from app.routers.operacion import router as operacion_router
from app.routers.simulador import router as simulador_router
from app.routers.stream import router as stream_router
from app.routers.telemetria import router as telemetria_router
from app.services.notificaciones import cerrar_notificaciones


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Una sola tarea de KPIs para toda la app; se cancela al apagarla."""
    tarea = asyncio.create_task(publicar_kpis_periodicos())
    try:
        yield
    finally:
        tarea.cancel()
        with suppress(asyncio.CancelledError):
            await tarea
        cerrar_notificaciones()


def create_app() -> FastAPI:
    """Arma la aplicación con CORS y el endpoint de salud."""
    settings = get_settings()
    # Corta el arranque antes de exponer la API con un secreto de demo.
    settings.validar_configuracion()
    app = FastAPI(title=settings.app_name, lifespan=_lifespan)

    origenes = [origen.strip() for origen in settings.cors_origins.split(",") if origen.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origenes or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Después de CORS: el log también ve los preflight y las respuestas de error.
    app.add_middleware(AccesoLogMiddleware)

    @app.get("/api/health")
    def salud() -> dict[str, int | bool]:
        """Sin autenticación: despierta Render y avisa el modo demo."""
        return {"ok": True, "escala_tiempo": settings.escala_tiempo}

    app.include_router(camaras_router)
    app.include_router(operacion_router)
    app.include_router(simulador_router)
    app.include_router(stream_router)
    app.include_router(telemetria_router)

    return app


app = create_app()
