"""Aplicación FastAPI de FríoTrack."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers.camaras import router as camaras_router
from app.routers.telemetria import router as telemetria_router


def create_app() -> FastAPI:
    """Arma la aplicación con CORS y el endpoint de salud."""
    settings = get_settings()
    # Corta el arranque antes de exponer la API con un secreto de demo.
    settings.validar_configuracion()
    app = FastAPI(title=settings.app_name)

    origenes = [origen.strip() for origen in settings.cors_origins.split(",") if origen.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origenes or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def salud() -> dict[str, int | bool]:
        """Sin autenticación: despierta Render y avisa el modo demo."""
        return {"ok": True, "escala_tiempo": settings.escala_tiempo}

    app.include_router(camaras_router)
    app.include_router(telemetria_router)

    return app


app = create_app()
