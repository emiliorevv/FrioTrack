"""Pruebas del guard de downgrade del baseline."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.engine import make_url

RUTA_BASELINE = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0001_esquema_inicial.py"
)
URL_SUPABASE = (
    "postgresql+psycopg://postgres:secreta"
    "@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
)


def _cargar_baseline() -> Any:
    spec = importlib.util.spec_from_file_location("migracion_0001", RUTA_BASELINE)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres@localhost:5432/friotrack",
        "postgresql+psycopg://postgres@127.0.0.1:5432/friotrack",
        "postgresql+psycopg://postgres@[::1]:5432/friotrack",
        "postgresql+psycopg://postgres@/friotrack?host=/tmp",
    ],
)
def test_puede_degradar_baseline_acepta_destinos_locales(url, monkeypatch):
    monkeypatch.delenv("PERMITIR_DOWNGRADE_BASELINE", raising=False)

    assert _cargar_baseline().puede_degradar_baseline(url) is True


def test_puede_degradar_baseline_rechaza_supabase(monkeypatch):
    monkeypatch.delenv("PERMITIR_DOWNGRADE_BASELINE", raising=False)

    assert _cargar_baseline().puede_degradar_baseline(URL_SUPABASE) is False


def test_puede_degradar_baseline_acepta_opt_in(monkeypatch):
    monkeypatch.setenv("PERMITIR_DOWNGRADE_BASELINE", "1")

    assert _cargar_baseline().puede_degradar_baseline(URL_SUPABASE) is True


def test_downgrade_usa_la_url_del_bind(monkeypatch):
    """El guard no se fía de ENTORNO local: mira el target real de la conexión."""
    monkeypatch.delenv("PERMITIR_DOWNGRADE_BASELINE", raising=False)
    modulo = _cargar_baseline()
    bind = SimpleNamespace(engine=SimpleNamespace(url=make_url(URL_SUPABASE)))
    monkeypatch.setattr(modulo, "op", SimpleNamespace(get_bind=lambda: bind))

    with pytest.raises(RuntimeError, match="PERMITIR_DOWNGRADE_BASELINE"):
        modulo.downgrade()
