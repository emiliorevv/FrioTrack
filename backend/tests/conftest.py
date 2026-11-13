"""Configuración común de pytest."""

import pytest

from app.config import limpiar_cache_settings


@pytest.fixture(autouse=True)
def _middleware_sin_base(monkeypatch):
    """Las pruebas no deben consultar ni escribir en Supabase por los logs."""
    monkeypatch.setenv("MIDDLEWARE_ACCESO_DB", "0")
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()
