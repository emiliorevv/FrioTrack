"""Pruebas del guard de downgrade del baseline."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

RUTA_BASELINE = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_esquema_inicial.py"
)


def _cargar_baseline() -> Any:
    spec = importlib.util.spec_from_file_location("migracion_0001", RUTA_BASELINE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_downgrade_del_baseline_falla_en_render(monkeypatch):
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setenv("ENTORNO", "local")

    with pytest.raises(RuntimeError, match="borraría todas las tablas"):
        _cargar_baseline().downgrade()


def test_downgrade_del_baseline_falla_fuera_de_local(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("ENTORNO", "produccion")

    with pytest.raises(RuntimeError, match="borraría todas las tablas"):
        _cargar_baseline().downgrade()
