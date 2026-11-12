"""Fixtures compartidas de las pruebas."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.db.base import Base


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Sesión sobre SQLite en memoria; nunca crea archivos en disco."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()
