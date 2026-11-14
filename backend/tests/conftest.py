"""Configuración común de pytest."""

import io

import pytest

from app.config import limpiar_cache_settings
from app.middleware import acceso


@pytest.fixture(autouse=True)
def _middleware_sin_base(monkeypatch):
    """Las pruebas no deben consultar ni escribir en Supabase por los logs."""
    monkeypatch.setenv("MIDDLEWARE_ACCESO_DB", "0")
    monkeypatch.setenv("ENTORNO", "local")
    monkeypatch.delenv("RENDER", raising=False)
    limpiar_cache_settings()
    acceso.limpiar_cache_bloqueos()
    yield
    acceso.limpiar_cache_bloqueos()
    limpiar_cache_settings()


@pytest.fixture
def log_stdout():
    """Apunta el logger de acceso a un buffer para leer la línea JSON emitida."""
    flujo = io.StringIO()
    manejador = acceso.logger_salida.handlers[0]
    anterior = manejador.setStream(flujo)
    try:
        yield flujo
    finally:
        manejador.setStream(anterior)
