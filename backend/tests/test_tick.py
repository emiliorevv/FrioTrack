"""Pruebas de POST /api/simulador/tick y del servicio del tick; sin base ni red."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.db.models import Camara
from app.db.session import get_db
from app.main import create_app
from app.routers import simulador as router_simulador
from app.schemas.telemetria import TelemetriaIn
from app.services import tick
from app.services.tick import (
    SENSOR_CRON,
    VENTANA_LECTURA_REAL,
    VENTANA_TICK,
    ejecutar_tick,
)

AHORA = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)

TOKEN_CRON = "token-cron-de-prueba"
AUTORIZACION = {"Authorization": f"Bearer {TOKEN_CRON}"}


@pytest.fixture(autouse=True)
def _entorno_de_pruebas(monkeypatch):
    """Aísla la configuración cacheada y fija el token del cron."""
    monkeypatch.setenv("ENTORNO", "local")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("CRON_TOKEN", TOKEN_CRON)
    monkeypatch.setenv("ESCALA_TIEMPO", "30")
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


# --- Dobles -----------------------------------------------------------------


class SesionFalsa:
    """Sesión mínima: entrega cámaras por id y cuenta rollbacks y locks."""

    def __init__(self, camaras: dict[int, Camara] | None = None) -> None:
        self.camaras = camaras or {}
        self.locks: list[int] = []
        self.rollbacks = 0

    def get(self, modelo: object, pk: object, **kwargs: object) -> Camara | None:
        assert modelo is Camara
        if kwargs.get("with_for_update") is not True:
            raise AssertionError("El tick debe bloquear la cámara antes de leerla.")
        self.locks.append(int(pk))  # type: ignore[arg-type]
        return self.camaras.get(int(pk))  # type: ignore[arg-type]

    def rollback(self) -> None:
        self.rollbacks += 1


def _camara(camara_id: int, nombre: str = "Pescados y mariscos", **cambios: object) -> Camara:
    base = {
        "id": camara_id,
        "nombre": nombre,
        "rango_min_c": Decimal("0.0"),
        "rango_max_c": Decimal("2.0"),
        "min_para_riesgo": 10,
        "min_para_merma": 60,
        "estado": "en_rango",
    }
    base.update(cambios)
    return Camara(**base)


def _preparar_tick(
    monkeypatch: pytest.MonkeyPatch,
    camaras: dict[int, Camara],
    *,
    escala_tiempo: int = 30,
    reales: frozenset[int] = frozenset(),
    ticks: frozenset[int] = frozenset(),
    falla_en: frozenset[int] = frozenset(),
) -> tuple[
    SesionFalsa,
    list[tuple[TelemetriaIn, Camara]],
    list[tuple[int, datetime, bool]],
    list[int],
]:
    """Sustituye los helpers del tick; regresa llamadas, consultas e intentos."""
    monkeypatch.setattr(tick, "utcnow", lambda: AHORA)
    monkeypatch.setattr(
        tick, "get_settings", lambda: SimpleNamespace(escala_tiempo=escala_tiempo)
    )
    monkeypatch.setattr(tick, "_ids_de_camaras", lambda _session: sorted(camaras))

    consultas: list[tuple[int, datetime, bool]] = []

    def hay_lectura_reciente(_session, camara_id, desde, *, solo_cron):
        consultas.append((camara_id, desde, solo_cron))
        return camara_id in (ticks if solo_cron else reales)

    monkeypatch.setattr(tick, "_hay_lectura_reciente", hay_lectura_reciente)

    llamadas: list[tuple[TelemetriaIn, Camara]] = []
    intentos: list[int] = []

    def procesar_lectura_falsa(_session, datos, camara):
        intentos.append(datos.camara_id)
        if datos.camara_id in falla_en:
            raise RuntimeError("falló el procesamiento")
        llamadas.append((datos, camara))
        return 500 + len(llamadas), "en_rango"

    monkeypatch.setattr(tick, "procesar_lectura", procesar_lectura_falsa)
    return SesionFalsa(camaras), llamadas, consultas, intentos


# --- Servicio ---------------------------------------------------------------


def test_tick_genera_una_lectura_por_camara_ordenada(monkeypatch):
    sesion, llamadas, _, _ = _preparar_tick(
        monkeypatch, {2: _camara(2, "Lácteos"), 1: _camara(1)}
    )

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (2, [])
    assert [datos.camara_id for datos, _ in llamadas] == [1, 2]
    assert sesion.locks == [1, 2]


def test_tick_salta_la_camara_con_lectura_real_dentro_de_la_ventana(monkeypatch):
    sesion, llamadas, consultas, _ = _preparar_tick(
        monkeypatch,
        {1: _camara(1), 2: _camara(2, "Lácteos")},
        reales=frozenset({1}),
    )

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (1, [1])
    assert [datos.camara_id for datos, _ in llamadas] == [2]
    # Con la lectura real no se llega a consultar el dedupe de ticks.
    assert consultas[:1] == [(1, AHORA - VENTANA_LECTURA_REAL, False)]
    assert (1, AHORA - VENTANA_TICK, True) not in consultas


def test_tick_salta_la_camara_con_un_tick_reciente(monkeypatch):
    sesion, llamadas, consultas, _ = _preparar_tick(
        monkeypatch, {1: _camara(1)}, ticks=frozenset({1})
    )

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (0, [1])
    assert llamadas == []
    assert consultas == [
        (1, AHORA - VENTANA_LECTURA_REAL, False),
        (1, AHORA - VENTANA_TICK, True),
    ]


def test_tick_reporta_varias_saltadas_en_orden(monkeypatch):
    sesion, llamadas, _, _ = _preparar_tick(
        monkeypatch,
        {3: _camara(3, "Verduras"), 1: _camara(1), 2: _camara(2, "Lácteos")},
        reales=frozenset({3}),
        ticks=frozenset({1}),
    )

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (1, [1, 3])
    assert [datos.camara_id for datos, _ in llamadas] == [2]


def test_tick_no_genera_sin_modo_demo(monkeypatch):
    def no_debe_consultar(*_args: object, **_kwargs: object) -> Any:
        raise AssertionError("Sin modo demo el tick no debe tocar la base.")

    monkeypatch.setattr(tick, "get_settings", lambda: SimpleNamespace(escala_tiempo=1))
    monkeypatch.setattr(tick, "_ids_de_camaras", no_debe_consultar)
    monkeypatch.setattr(tick, "_hay_lectura_reciente", no_debe_consultar)
    monkeypatch.setattr(tick, "procesar_lectura", no_debe_consultar)

    assert ejecutar_tick(SesionFalsa()) == (0, [])


def test_tick_continua_si_falla_una_camara(monkeypatch):
    sesion, llamadas, _, intentos = _preparar_tick(
        monkeypatch,
        {1: _camara(1), 2: _camara(2), 3: _camara(3)},
        falla_en=frozenset({2}),
    )

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (2, [])
    assert intentos == [1, 2, 3]
    assert [datos.camara_id for datos, _ in llamadas] == [1, 3]
    assert sesion.rollbacks == 1


def test_tick_arma_la_lectura_con_sensor_cron_humedad_y_rango(monkeypatch):
    sesion, llamadas, _, _ = _preparar_tick(monkeypatch, {1: _camara(1)})

    ejecutar_tick(sesion)

    (datos, camara) = llamadas[0]
    assert camara.id == 1
    assert datos.sensor_id == SENSOR_CRON
    assert datos.camara_id == 1
    assert datos.ts == AHORA
    assert datos.ts.tzinfo is not None
    assert datos.humedad_pct == 80.0
    assert datos.puerta_abierta is False
    assert 0.0 <= datos.temperatura_c <= 2.0


def test_tick_usa_las_ventanas_exactas(monkeypatch):
    sesion, _, consultas, _ = _preparar_tick(monkeypatch, {1: _camara(1)})

    ejecutar_tick(sesion)

    assert consultas == [
        (1, AHORA - timedelta(minutes=2), False),
        (1, AHORA - timedelta(seconds=30), True),
    ]


def test_tick_se_salta_una_camara_inexistente(monkeypatch):
    sesion, llamadas, _, _ = _preparar_tick(monkeypatch, {1: _camara(1)})
    monkeypatch.setattr(tick, "_ids_de_camaras", lambda _session: [1, 2])

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (1, [])
    assert sesion.locks == [1, 2]
    assert [datos.camara_id for datos, _ in llamadas] == [1]


# --- Router -----------------------------------------------------------------


def _cliente(monkeypatch: pytest.MonkeyPatch, resultado=(4, [1])):
    """TestClient con el servicio del tick y la sesión sustituidos por dobles."""
    llamadas: list[object] = []

    def tick_falso(session: object) -> tuple[int, list[int]]:
        llamadas.append(session)
        return resultado

    monkeypatch.setattr(router_simulador, "ejecutar_tick", tick_falso)
    app = create_app()

    def sesion_falsa():
        yield None

    app.dependency_overrides[get_db] = sesion_falsa
    return TestClient(app), llamadas


def test_post_tick_responde_202_con_lecturas_y_saltadas(monkeypatch):
    cliente, llamadas = _cliente(monkeypatch)

    with cliente:
        respuesta = cliente.post("/api/simulador/tick", headers=AUTORIZACION)

    assert respuesta.status_code == 202
    assert respuesta.json() == {"lecturas": 4, "saltadas": [1]}
    assert llamadas == [None]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer    "},
        {"Authorization": TOKEN_CRON},
        {"Authorization": "Basic dXN1YXJpbzpwYXNz"},
        {"Authorization": "Bearer token-equivocado"},
    ],
    ids=[
        "sin-header",
        "header-vacio",
        "solo-bearer",
        "bearer-sin-token",
        "bearer-solo-espacios",
        "token-sin-prefijo",
        "otro-esquema",
        "token-incorrecto",
    ],
)
def test_post_tick_sin_token_valido_responde_401(monkeypatch, headers):
    def no_debe_ejecutar(_session: object) -> tuple[int, list[int]]:
        raise AssertionError("El router debió rechazar el token antes del servicio.")

    monkeypatch.setattr(router_simulador, "ejecutar_tick", no_debe_ejecutar)
    app = create_app()

    def sesion_falsa():
        yield None

    app.dependency_overrides[get_db] = sesion_falsa

    with TestClient(app) as cliente:
        respuesta = cliente.post("/api/simulador/tick", headers=headers)

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert "Bearer" in respuesta.json()["detail"]
    assert TOKEN_CRON not in respuesta.json()["detail"]


@pytest.mark.parametrize("cron_token", ["", "   "], ids=["vacio", "en-blanco"])
def test_post_tick_sin_cron_token_configurado_responde_401(monkeypatch, cron_token):
    monkeypatch.setenv("CRON_TOKEN", cron_token)
    limpiar_cache_settings()

    def no_debe_ejecutar(_session: object) -> tuple[int, list[int]]:
        raise AssertionError("Sin CRON_TOKEN no debe ejecutarse el tick.")

    monkeypatch.setattr(router_simulador, "ejecutar_tick", no_debe_ejecutar)
    app = create_app()

    def sesion_falsa():
        yield None

    app.dependency_overrides[get_db] = sesion_falsa

    with TestClient(app) as cliente:
        respuesta = cliente.post("/api/simulador/tick", headers=AUTORIZACION)

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_post_tick_sin_token_registra_el_intento_del_cron(log_stdout):
    """El 401 debe conservar credencial y sujeto para la regla SIEM."""
    app = create_app()

    def sesion_falsa():
        yield None

    app.dependency_overrides[get_db] = sesion_falsa

    with TestClient(app) as cliente:
        respuesta = cliente.post("/api/simulador/tick")

    assert respuesta.status_code == 401
    lineas = [json.loads(linea) for linea in log_stdout.getvalue().splitlines() if linea]
    evento = next(linea for linea in lineas if linea["ruta"] == "/api/simulador/tick")
    assert evento["credencial"] == "cron"
    assert evento["sujeto"] == "SIM-CRON"
    assert evento["status"] == 401
