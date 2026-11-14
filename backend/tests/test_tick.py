"""Pruebas de POST /api/simulador/tick y del servicio del tick; sin base ni red."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.db.models import Camara, Lectura
from app.db.session import get_db
from app.main import create_app
from app.routers import simulador as router_simulador
from app.schemas.telemetria import TelemetriaIn
from app.services import tick
from app.services.tick import SENSOR_CRON, VENTANA_LECTURA_REAL, ejecutar_tick

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
    """Sesión mínima: lista cámaras y detecta lecturas reales recientes."""

    def __init__(
        self,
        camaras: list[Camara] | None = None,
        lecturas: list[Lectura] | None = None,
    ) -> None:
        self.camaras = camaras or []
        self.lecturas = lecturas or []
        self.consultas: list[Any] = []

    def scalars(self, stmt: Any) -> Any:
        sql = str(stmt).lower()
        self.consultas.append(stmt)

        if "from camaras" in sql:
            return sorted(self.camaras, key=lambda camara: camara.id)
        if "from lecturas" in sql:
            params = stmt.compile().params
            desde = next(
                valor for clave, valor in params.items() if clave.startswith("recibida_en_")
            )
            sensor = next(
                valor for clave, valor in params.items() if clave.startswith("sensor_id_")
            )
            return {
                lectura.camara_id
                for lectura in self.lecturas
                if lectura.recibida_en >= desde and lectura.sensor_id != sensor
            }
        raise AssertionError(f"Consulta no soportada por la sesión falsa:\n{stmt}")


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


def _lectura(
    camara_id: int,
    sensor_id: str = "S-PES-01",
    recibida_en: datetime = AHORA,
) -> Lectura:
    return Lectura(
        id=1,
        camara_id=camara_id,
        sensor_id=sensor_id,
        ts=recibida_en,
        recibida_en=recibida_en,
        temperatura_c=Decimal("1.0"),
        humedad_pct=Decimal("80.0"),
        puerta_abierta=False,
    )


def _preparar_tick(monkeypatch: pytest.MonkeyPatch) -> list[TelemetriaIn]:
    """Fija la hora y sustituye `procesar_lectura`; regresa las llamadas."""
    monkeypatch.setattr(tick, "utcnow", lambda: AHORA)
    llamadas: list[TelemetriaIn] = []

    def procesar_lectura_falsa(_session: object, datos: TelemetriaIn):
        llamadas.append(datos)
        return 500 + len(llamadas), "en_rango"

    monkeypatch.setattr(tick, "procesar_lectura", procesar_lectura_falsa)
    return llamadas


# --- Servicio ---------------------------------------------------------------


def test_tick_genera_una_lectura_por_camara_sin_datos_recientes(monkeypatch):
    llamadas = _preparar_tick(monkeypatch)
    sesion = SesionFalsa(camaras=[_camara(2, "Lácteos"), _camara(1)])

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (2, [])
    # Las cámaras se recorren ordenadas por id, sin importar el orden de la base.
    assert [datos.camara_id for datos in llamadas] == [1, 2]


def test_tick_salta_la_camara_con_lectura_real_dentro_de_la_ventana(monkeypatch):
    llamadas = _preparar_tick(monkeypatch)
    sesion = SesionFalsa(
        camaras=[_camara(1), _camara(2, "Lácteos")],
        lecturas=[_lectura(1, recibida_en=AHORA - timedelta(seconds=30))],
    )

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (1, [1])
    assert [datos.camara_id for datos in llamadas] == [2]


def test_tick_no_salta_por_una_lectura_real_mas_vieja_que_la_ventana(monkeypatch):
    llamadas = _preparar_tick(monkeypatch)
    vieja = AHORA - VENTANA_LECTURA_REAL - timedelta(seconds=1)
    sesion = SesionFalsa(camaras=[_camara(1)], lecturas=[_lectura(1, recibida_en=vieja)])

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (1, [])
    assert [datos.camara_id for datos in llamadas] == [1]


def test_tick_no_cuenta_una_lectura_previa_del_cron_como_real(monkeypatch):
    llamadas = _preparar_tick(monkeypatch)
    sesion = SesionFalsa(
        camaras=[_camara(1)],
        lecturas=[_lectura(1, sensor_id=SENSOR_CRON, recibida_en=AHORA - timedelta(seconds=10))],
    )

    generadas, saltadas = ejecutar_tick(sesion)

    assert (generadas, saltadas) == (1, [])
    assert len(llamadas) == 1


def test_tick_arma_la_lectura_con_sensor_cron_humedad_y_rango(monkeypatch):
    llamadas = _preparar_tick(monkeypatch)
    sesion = SesionFalsa(camaras=[_camara(1)])

    ejecutar_tick(sesion)

    (datos,) = llamadas
    assert datos.sensor_id == SENSOR_CRON
    assert datos.camara_id == 1
    assert datos.ts == AHORA
    assert datos.ts.tzinfo is not None
    assert datos.humedad_pct == 80.0
    assert datos.puerta_abierta is False
    assert 0.0 <= datos.temperatura_c <= 2.0


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


def test_post_tick_sin_cron_token_configurado_responde_401(monkeypatch):
    monkeypatch.setenv("CRON_TOKEN", "")
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
