"""Pruebas de POST /api/telemetria y del servicio de ingesta; sin base ni red."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.db.models import Alerta, Camara, Lectura, Lote, Sensor
from app.db.session import get_db
from app.main import create_app
from app.routers import telemetria as router_telemetria
from app.schemas.telemetria import TelemetriaIn
from app.services import telemetria as servicio
from app.services.telemetria import procesar_telemetria

AHORA = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _entorno_de_pruebas(monkeypatch):
    """Aísla la configuración cacheada y usa la escala de demo en las reglas."""
    monkeypatch.setenv("ENTORNO", "local")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("ESCALA_TIEMPO", "30")
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def _payload(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "sensor_id": "S-PES-01",
        "camara_id": 1,
        "ts": "2026-11-18T13:05:00-06:00",
        "temperatura_c": 1.4,
        "humedad_pct": 88,
        "puerta_abierta": False,
    }
    base.update(cambios)
    return base


def _datos(**cambios: object) -> TelemetriaIn:
    return TelemetriaIn(**_payload(**cambios))


def _cliente(monkeypatch: pytest.MonkeyPatch, resultado=(18342, "en_rango")):
    """TestClient con el servicio y la sesión sustituidos por dobles."""
    llamadas: list[TelemetriaIn] = []

    def servicio_falso(_session: object, datos: TelemetriaIn) -> tuple[int, str]:
        llamadas.append(datos)
        return resultado

    monkeypatch.setattr(router_telemetria, "procesar_telemetria", servicio_falso)
    app = create_app()

    def sesion_falsa():
        yield None

    app.dependency_overrides[get_db] = sesion_falsa
    return TestClient(app), llamadas


class SesionFalsa:
    """Sesión mínima: resuelve cámara/sensor y registra escrituras sin conexión."""

    def __init__(self, camara: Camara | None, sensor: Sensor | None) -> None:
        self.camara = camara
        self.sensor = sensor
        self.agregados: list[object] = []
        self.flushes = 0
        self.commits = 0
        self.siguiente_id = 500

    def get(self, modelo: object, _pk: object) -> object | None:
        if modelo is Camara:
            return self.camara
        if modelo is Sensor:
            return self.sensor
        raise AssertionError(f"Modelo inesperado: {modelo!r}")

    def add(self, fila: object) -> None:
        self.agregados.append(fila)

    def flush(self) -> None:
        self.flushes += 1
        for fila in self.agregados:
            if isinstance(fila, Lectura) and fila.id is None:
                fila.id = self.siguiente_id

    def commit(self) -> None:
        self.commits += 1


def _camara(**cambios: object) -> Camara:
    base = {
        "id": 1,
        "nombre": "Pescados y mariscos",
        "rango_min_c": Decimal("0.0"),
        "rango_max_c": Decimal("2.0"),
        "min_para_riesgo": 10,
        "min_para_merma": 60,
        "estado": "en_rango",
    }
    base.update(cambios)
    return Camara(**base)


def _sensor(**cambios: object) -> Sensor:
    base = {"id": "S-PES-01", "camara_id": 1, "token_hash": "hash", "activo": True}
    base.update(cambios)
    return Sensor(**base)


def _lote(estado: str = "ok", producto: str = "Robalo fresco", lote_id: int = 1) -> Lote:
    return Lote(
        id=lote_id,
        producto=producto,
        camara_id=1,
        cantidad=Decimal("12.00"),
        unidad="kg",
        costo_total_mxn=Decimal("3240.00"),
        caducidad=date(2026, 11, 20),
        estado=estado,
    )


# --- Router -----------------------------------------------------------------


def test_post_telemetria_responde_202_con_lectura_y_estado(monkeypatch):
    cliente, llamadas = _cliente(monkeypatch)

    with cliente:
        respuesta = cliente.post("/api/telemetria", json=_payload())

    assert respuesta.status_code == 202
    assert respuesta.json() == {"lectura_id": 18342, "estado_camara": "en_rango"}
    assert len(llamadas) == 1
    assert llamadas[0].sensor_id == "S-PES-01"
    assert llamadas[0].camara_id == 1


@pytest.mark.parametrize(
    "cambios",
    [
        {"temperatura_c": -40.1},
        {"temperatura_c": 60.1},
        {"humedad_pct": -0.1},
        {"humedad_pct": 100.1},
        {"ts": "2026-11-18T19:05:00"},
        {"ts": "2026-11-18"},
    ],
    ids=[
        "temperatura-baja",
        "temperatura-alta",
        "humedad-baja",
        "humedad-alta",
        "ts-sin-zona",
        "fecha-sin-hora-ni-zona",
    ],
)
def test_telemetria_invalida_responde_422(monkeypatch, cambios):
    def no_debe_procesar(_session: object, _datos: TelemetriaIn) -> tuple[int, str]:
        raise AssertionError("La validación debió rechazar la lectura antes del servicio.")

    monkeypatch.setattr(router_telemetria, "procesar_telemetria", no_debe_procesar)
    app = create_app()

    def sesion_falsa():
        yield None

    app.dependency_overrides[get_db] = sesion_falsa

    with TestClient(app) as cliente:
        respuesta = cliente.post("/api/telemetria", json=_payload(**cambios))

    assert respuesta.status_code == 422


# --- Servicio ---------------------------------------------------------------


def test_servicio_camara_inexistente_responde_404():
    with pytest.raises(HTTPException) as error:
        procesar_telemetria(SesionFalsa(camara=None, sensor=None), _datos())

    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "sensor",
    [None, _sensor(activo=False), _sensor(camara_id=2)],
    ids=["inexistente", "inactivo", "de-otra-camara"],
)
def test_servicio_sensor_no_autorizado_responde_403(sensor):
    sesion = SesionFalsa(camara=_camara(), sensor=sensor)

    with pytest.raises(HTTPException) as error:
        procesar_telemetria(sesion, _datos())

    assert error.value.status_code == 403


def test_servicio_lectura_normal_persiste_y_queda_en_rango(monkeypatch):
    monkeypatch.setattr(servicio, "utcnow", lambda: AHORA)
    monkeypatch.setattr(servicio, "_cargar_lotes", lambda _s, _c: [_lote()])
    monkeypatch.setattr(servicio, "_cargar_alertas_abiertas", lambda _s, _c: [])
    sesion = SesionFalsa(camara=_camara(), sensor=_sensor())

    lectura_id, estado = procesar_telemetria(sesion, _datos(temperatura_c=1.0))

    lectura = sesion.agregados[0]
    assert isinstance(lectura, Lectura)
    assert lectura_id == sesion.siguiente_id == lectura.id
    assert lectura.recibida_en == AHORA
    assert lectura.sospechosa is False
    assert sesion.camara.ultima_lectura_id == lectura_id
    assert sesion.camara.fuera_de_rango_desde is None
    assert sesion.camara.puerta_abierta_desde is None
    assert estado == "en_rango"
    assert sesion.flushes == 1
    assert sesion.commits == 1


def test_servicio_abre_alerta_y_pasa_lote_a_riesgo_en_el_umbral(monkeypatch):
    monkeypatch.setattr(servicio, "utcnow", lambda: AHORA)
    camara = _camara(fuera_de_rango_desde=AHORA - timedelta(seconds=20))
    lote_ok = _lote("ok", lote_id=1)
    lote_merma = _lote("merma", "Camarón", lote_id=2)
    monkeypatch.setattr(
        servicio, "_cargar_lotes", lambda _s, _c: [lote_ok, lote_merma]
    )
    monkeypatch.setattr(servicio, "_cargar_alertas_abiertas", lambda _s, _c: [])
    sesion = SesionFalsa(camara=camara, sensor=_sensor())

    lectura_id, estado = procesar_telemetria(sesion, _datos(temperatura_c=3.0))

    assert lectura_id == sesion.siguiente_id
    assert lote_ok.estado == "en_riesgo"
    assert lote_merma.estado == "merma"
    assert estado == "critica"
    assert camara.estado == "critica"

    alertas = [fila for fila in sesion.agregados if isinstance(fila, Alerta)]
    assert len(alertas) == 1
    assert alertas[0].camara_id == camara.id
    assert alertas[0].tipo == "temperatura"
    assert alertas[0].abierta_en == AHORA
    assert alertas[0].temperatura_max_c == Decimal("3.0")
    assert alertas[0].sms_enviados == 0


def test_servicio_marca_merma_con_su_fecha(monkeypatch):
    monkeypatch.setattr(servicio, "utcnow", lambda: AHORA)
    camara = _camara(fuera_de_rango_desde=AHORA - timedelta(seconds=120))
    lote = _lote("en_riesgo")
    monkeypatch.setattr(servicio, "_cargar_lotes", lambda _s, _c: [lote])
    monkeypatch.setattr(servicio, "_cargar_alertas_abiertas", lambda _s, _c: [])
    sesion = SesionFalsa(camara=camara, sensor=_sensor())

    _, estado = procesar_telemetria(sesion, _datos(temperatura_c=3.0))

    assert lote.estado == "merma"
    assert lote.merma_en == AHORA
    assert estado == "critica"


def test_servicio_abre_alerta_de_puerta_y_queda_en_alerta(monkeypatch):
    monkeypatch.setattr(servicio, "utcnow", lambda: AHORA)
    camara = _camara(puerta_abierta_desde=AHORA - timedelta(seconds=10))
    monkeypatch.setattr(servicio, "_cargar_lotes", lambda _s, _c: [_lote()])
    monkeypatch.setattr(servicio, "_cargar_alertas_abiertas", lambda _s, _c: [])
    sesion = SesionFalsa(camara=camara, sensor=_sensor())

    _, estado = procesar_telemetria(sesion, _datos(puerta_abierta=True))

    assert estado == "alerta"
    alertas = [fila for fila in sesion.agregados if isinstance(fila, Alerta)]
    assert len(alertas) == 1
    assert alertas[0].tipo == "puerta"
    assert alertas[0].sms_enviados == 0


def test_servicio_cierra_alertas_y_recupera_lotes_al_volver_al_rango(monkeypatch):
    monkeypatch.setattr(servicio, "utcnow", lambda: AHORA)
    camara = _camara(fuera_de_rango_desde=AHORA - timedelta(minutes=5))
    alerta_temperatura = Alerta(
        camara_id=1,
        tipo="temperatura",
        abierta_en=AHORA - timedelta(minutes=5),
        temperatura_max_c=Decimal("3.1"),
        sms_enviados=0,
    )
    alerta_puerta = Alerta(
        camara_id=1,
        tipo="puerta",
        abierta_en=AHORA - timedelta(minutes=2),
        sms_enviados=0,
    )
    lote = _lote("en_riesgo")
    monkeypatch.setattr(servicio, "_cargar_lotes", lambda _s, _c: [lote])
    monkeypatch.setattr(
        servicio,
        "_cargar_alertas_abiertas",
        lambda _s, _c: [alerta_temperatura, alerta_puerta],
    )
    sesion = SesionFalsa(camara=camara, sensor=_sensor())

    _, estado = procesar_telemetria(sesion, _datos(temperatura_c=1.0))

    assert camara.fuera_de_rango_desde is None
    assert camara.puerta_abierta_desde is None
    assert alerta_temperatura.cerrada_en == AHORA
    assert alerta_puerta.cerrada_en == AHORA
    assert lote.estado == "ok"
    assert estado == "en_rango"
    assert sesion.commits == 1
