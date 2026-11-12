"""Aplicación FastAPI de FríoTrack."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


def create_app() -> FastAPI:
    """Arma la aplicación con CORS y el endpoint de salud."""
    settings = get_settings()
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

    return app


app = create_app()
