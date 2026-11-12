"""Pruebas de la validación de configuración (JWT_SECRET en producción)."""

import pytest

from app.config import JWT_SECRET_POR_DEFECTO, get_settings, limpiar_cache_settings
from app.main import create_app

SECRETO_FUERTE = "secreto-de-produccion-con-32-o-mas-caracteres"


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    """Cada prueba lee el entorno que monkeypatch acaba de definir."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def test_local_con_secreto_por_defecto_no_lanza(monkeypatch):
    monkeypatch.setenv("ENTORNO", "local")
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET_POR_DEFECTO)

    get_settings().validar_configuracion()  # no debe lanzar


def test_produccion_con_secreto_por_defecto_lanza(monkeypatch):
    monkeypatch.setenv("ENTORNO", "produccion")
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET_POR_DEFECTO)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings().validar_configuracion()


def test_produccion_con_secreto_corto_lanza(monkeypatch):
    monkeypatch.setenv("ENTORNO", "produccion")
    monkeypatch.setenv("JWT_SECRET", "corto")

    with pytest.raises(RuntimeError, match="32 caracteres"):
        get_settings().validar_configuracion()


def test_produccion_con_secreto_fuerte_no_lanza(monkeypatch):
    monkeypatch.setenv("ENTORNO", "produccion")
    monkeypatch.setenv("JWT_SECRET", SECRETO_FUERTE)

    get_settings().validar_configuracion()  # no debe lanzar


def test_create_app_en_produccion_con_secreto_por_defecto_lanza(monkeypatch):
    monkeypatch.setenv("ENTORNO", "produccion")
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET_POR_DEFECTO)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_app()
