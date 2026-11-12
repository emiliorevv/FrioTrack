"""Motor, fábrica de sesiones y dependencia de base de datos."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

# Sin `bind`: el motor se crea hasta la primera petición (importar no toca disco).
SessionLocal = sessionmaker(expire_on_commit=False)
_engine: Engine | None = None


def crear_engine(database_url: str | None = None) -> Engine:
    """Crea el motor con opciones adecuadas para SQLite (pruebas) o Postgres."""
    url = database_url or get_settings().database_url
    opciones: dict[str, Any] = {}
    if url.startswith("sqlite"):
        opciones["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            opciones["poolclass"] = StaticPool
    else:
        opciones["pool_pre_ping"] = True
    return create_engine(url, **opciones)


def get_engine() -> Engine:
    """Devuelve el motor compartido, creándolo en el primer uso."""
    global _engine
    if _engine is None:
        _engine = crear_engine()
    return _engine


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: una sesión por petición."""
    with SessionLocal(bind=get_engine()) as session:
        yield session
