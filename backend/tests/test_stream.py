"""Pruebas de GET /api/stream: se leen solo los primeros trozos y se cierra."""

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.main import create_app
from app.realtime.bus import EVENTO_CERRAR, EventBus
from app.routers import stream as stream_mod

KPIS = {
    "pct_tiempo_en_rango_24h": 100.0,
    "alertas_activas": 1,
    "tiempo_respuesta_promedio_min": 0.0,
    "valor_en_riesgo_mxn": 0.0,
    "merma_hoy_mxn": 0.0,
    "merma_mes_mxn": 0.0,
}


class _RequestFalsa:
    """Request mínima: el stream solo pregunta si el cliente sigue conectado."""

    async def is_disconnected(self) -> bool:
        return False


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    """Aísla cada prueba de la configuración cacheada."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


@pytest.fixture(autouse=True)
def _kpis_y_cupo_limpios(monkeypatch):
    """Evita tocar Postgres y que el cupo se arrastre entre pruebas."""
    monkeypatch.setattr(stream_mod, "calcular_kpis_actuales", lambda: KPIS)
    monkeypatch.setattr(
        stream_mod,
        "limite_conexiones",
        stream_mod.LimiteConexiones(stream_mod.MAX_CONEXIONES_STREAM),
    )


@pytest.mark.parametrize("params", [{}, {"token": "jwt-pendiente"}], ids=["sin-token", "con-token"])
def test_stream_responde_sse_con_retry_y_kpis_iniciales(params):
    app = create_app()

    with TestClient(app) as cliente:
        with cliente.stream("GET", "/api/stream", params=params) as respuesta:
            assert respuesta.status_code == 200
            assert respuesta.headers["content-type"].startswith("text/event-stream")
            assert respuesta.headers["cache-control"] == "no-cache"
            assert respuesta.headers["x-accel-buffering"] == "no"
            trozos = respuesta.iter_text()
            primera = next(trozos)
            segunda = next(trozos)

    assert "retry: 3000" in primera
    # El primer KPI llega al suscribirse, no 30 s después.
    assert segunda.startswith("event: kpis")
    assert '"alertas_activas":1' in segunda


def test_stream_regresa_503_cuando_se_llena_el_cupo(monkeypatch):
    monkeypatch.setattr(stream_mod, "limite_conexiones", stream_mod.LimiteConexiones(1))
    app = create_app()

    with TestClient(app) as cliente:
        with cliente.stream("GET", "/api/stream") as primera:
            assert primera.status_code == 200
            segunda = cliente.get("/api/stream")

    assert segunda.status_code == 503
    assert "conexiones SSE" in segunda.json()["detail"]


def test_stream_manda_ping_cuando_no_hay_eventos(monkeypatch):
    monkeypatch.setattr(stream_mod, "ESPERA_EVENTO_SEGUNDOS", 0.01)

    async def escenario():
        generador = stream_mod._eventos(_RequestFalsa())
        try:
            await anext(generador)  # retry
            await anext(generador)  # kpis inicial
            return await asyncio.wait_for(anext(generador), timeout=1)
        finally:
            await generador.aclose()

    assert asyncio.run(escenario()) == stream_mod.PING


def test_stream_termina_al_recibir_cerrar(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(stream_mod, "bus", bus)

    async def escenario():
        generador = stream_mod._eventos(_RequestFalsa())
        try:
            await anext(generador)  # retry
            await anext(generador)  # kpis inicial
            bus.publicar(EVENTO_CERRAR, {})
            with pytest.raises(StopAsyncIteration):
                await asyncio.wait_for(anext(generador), timeout=1)
        finally:
            await generador.aclose()

    asyncio.run(escenario())


def test_limite_de_conexiones_se_libera_al_desuscribir():
    limite = stream_mod.LimiteConexiones(1)

    limite.adquirir()
    with pytest.raises(HTTPException) as excepcion:
        limite.adquirir()
    limite.liberar()
    limite.adquirir()  # el cupo volvió a estar libre

    assert excepcion.value.status_code == 503
