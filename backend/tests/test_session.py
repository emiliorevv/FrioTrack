"""Pruebas del motor de base de datos: no abren conexión ni tocan la red."""

import pytest
from sqlalchemy.engine import Engine

from app.config import limpiar_cache_settings
from app.db.session import MENSAJE_SIN_DATABASE_URL, crear_engine

URL_EJEMPLO = (
    "postgresql+psycopg://postgres.ref:password"
    "@aws-0-region.pooler.supabase.com:5432/postgres?sslmode=require"
)


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def test_sin_database_url_falla_con_mensaje_claro(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")

    with pytest.raises(RuntimeError) as error:
        crear_engine()

    mensaje = str(error.value)
    assert mensaje == MENSAJE_SIN_DATABASE_URL
    assert ".env" in mensaje
    assert "Session Pooler" in mensaje
    assert "Supabase" in mensaje


def test_crear_engine_lee_database_url_de_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL_EJEMPLO)

    engine = crear_engine()

    assert isinstance(engine, Engine)
    assert engine.dialect.name == "postgresql"
    assert engine.pool._pre_ping is True
    engine.dispose()


def test_crear_engine_acepta_una_url_explicita():
    engine = crear_engine(URL_EJEMPLO)

    assert engine.dialect.name == "postgresql"
    engine.dispose()
