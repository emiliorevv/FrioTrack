"""Pruebas de la verificación de esquema previa a cargar el seed."""

import pytest
from sqlalchemy import create_engine

from app.db import init_db


def test_inicializar_db_sin_esquema_pide_migraciones(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(init_db, "get_engine", lambda: engine)

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        init_db.inicializar_db()
