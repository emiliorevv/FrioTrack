"""Configuración común de pytest."""

import io
from concurrent.futures import Future

import pytest

from app.config import limpiar_cache_settings
from app.middleware import acceso
from app.services import notificaciones


class EjecutorSincrono:
    """Ejecutor de prueba: corre el envío en el mismo hilo, sin hilos pendientes."""

    def submit(self, fn, *args, **kwargs):
        futuro = Future()
        try:
            futuro.set_result(fn(*args, **kwargs))
        except Exception as error:
            futuro.set_exception(error)
        return futuro

    def shutdown(self, **kwargs):
        """Cumple la interfaz de ThreadPoolExecutor; no hay nada que apagar."""


@pytest.fixture(autouse=True)
def _notificaciones_sincronas(monkeypatch):
    """Las notificaciones se envían inline para que las pruebas sean deterministas."""
    monkeypatch.setattr(notificaciones, "_executor", EjecutorSincrono())


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
