"""Pruebas de la verificación de revisión previa a cargar el seed."""

import runpy

import pytest
from sqlalchemy import create_engine

from app.db import init_db


def test_inicializar_db_sin_esquema_pide_migraciones(monkeypatch):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(init_db, "get_engine", lambda: engine)

    with pytest.raises(RuntimeError, match="python -m app.db.migrar"):
        init_db.inicializar_db()


def test_inicializar_db_carga_seed_con_esquema_al_dia(monkeypatch):
    engine = create_engine("sqlite://")
    sesiones = []

    def cargar_seed(session):
        sesiones.append(session)
        return True

    monkeypatch.setattr(init_db, "get_engine", lambda: engine)
    monkeypatch.setattr(init_db, "esquema_actualizado", lambda _: True)
    monkeypatch.setattr(init_db, "cargar_seed", cargar_seed)

    assert init_db.inicializar_db() is True
    assert len(sesiones) == 1


def test_main_sin_esquema_termina_con_mensaje(monkeypatch):
    monkeypatch.setattr("app.db.session.get_engine", lambda: create_engine("sqlite://"))

    with pytest.raises(SystemExit) as salida:
        runpy.run_module("app.db.init_db", run_name="__main__")

    assert "python -m app.db.migrar" in str(salida.value)
