"""Pruebas del endpoint GET /api/health."""

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    """Cada prueba arma la app desde cero para leer el entorno actual."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def _cliente() -> TestClient:
    return TestClient(create_app())


def test_health_responde_200_con_cuerpo_esperado(monkeypatch):
    monkeypatch.setenv("ESCALA_TIEMPO", "1")

    with _cliente() as cliente:
        respuesta = cliente.get("/api/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True, "escala_tiempo": 1}


def test_health_respeta_escala_tiempo_del_entorno(monkeypatch):
    monkeypatch.setenv("ESCALA_TIEMPO", "30")

    with _cliente() as cliente:
        respuesta = cliente.get("/api/health")

    assert respuesta.status_code == 200
    assert respuesta.json()["escala_tiempo"] == 30


def test_health_no_exige_autenticacion(monkeypatch):
    monkeypatch.setenv("ESCALA_TIEMPO", "1")

    with _cliente() as cliente:
        sin_cabecera = cliente.get("/api/health")
        con_token_invalido = cliente.get(
            "/api/health", headers={"Authorization": "Bearer token-que-no-existe"}
        )

    assert sin_cabecera.status_code == 200
    assert con_token_invalido.status_code == 200
