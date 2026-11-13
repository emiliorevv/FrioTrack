"""Pruebas de GET /api/stream: se lee solo el primer trozo y se cierra."""

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    """Aísla cada prueba de la configuración cacheada."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


@pytest.mark.parametrize("params", [{}, {"token": "jwt-pendiente"}], ids=["sin-token", "con-token"])
def test_stream_responde_sse_con_retry_inicial(params):
    app = create_app()

    with TestClient(app) as cliente:
        with cliente.stream("GET", "/api/stream", params=params) as respuesta:
            assert respuesta.status_code == 200
            assert respuesta.headers["content-type"].startswith("text/event-stream")
            assert respuesta.headers["cache-control"] == "no-cache"
            assert respuesta.headers["x-accel-buffering"] == "no"
            primera = next(respuesta.iter_text())

    assert "retry: 3000" in primera
