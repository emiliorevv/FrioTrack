"""Base declarativa y utilidades comunes de la base de datos."""

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Devuelve la hora actual en UTC, con zona horaria."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base de todos los modelos SQLAlchemy."""
