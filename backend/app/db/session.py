"""Motor, fábrica de sesiones y dependencia de base de datos (Postgres en Supabase)."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

# Sin `bind`: el motor se crea hasta el primer uso (importar no se conecta a nada).
SessionLocal = sessionmaker(expire_on_commit=False)
_engine: Engine | None = None

MENSAJE_SIN_DATABASE_URL = (
    "DATABASE_URL no está configurada. Crea backend/.env a partir de backend/.env.example "
    "y pega la URI «Session Pooler» de Supabase (Project Settings → Database), por ejemplo: "
    "postgresql+psycopg://postgres.<project-ref>:<password>"
    "@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
)


def crear_engine(database_url: str | None = None) -> Engine:
    """Crea el motor; el engine es lazy y no abre conexión hasta la primera consulta."""
    url = database_url if database_url is not None else get_settings().database_url
    if not url or not url.strip():
        raise RuntimeError(MENSAJE_SIN_DATABASE_URL)
    return create_engine(url.strip(), pool_pre_ping=True)


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
