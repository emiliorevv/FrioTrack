"""Pruebas de los endpoints de simulación de la demo (sin base ni sleeps reales)."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.core.auth import crear_token, get_restaurante_id, sesion_si_auth
from app.db.models import (
    RESTAURANTE_DEMO_ID,
    AlertaSeguridad,
    Camara,
    IpBloqueada,
    Sensor,
    Usuario,
)
from app.db.seed import construir_seed
from app.db.session import get_db
from app.main import create_app
from app.routers import demo as demo_mod

TOKENS = {
    "S-PES-01": "token-pescados",
    "S-CAR-01": "token-carnes",
    "S-LAC-01": "token-lacteos",
    "S-VER-01": "token-verduras",
    "S-CON-01": "token-congelador",
}


class SesionFalsa:
    """Sesión mínima para los endpoints de demo y el alta de la alerta SIEM."""

    def __init__(
        self,
        camaras: list[Camara] | None = None,
        sensores: list[Sensor] | None = None,
    ) -> None:
        self.camaras = {camara.id: camara for camara in camaras or []}
        self.sensores = {sensor.id: sensor for sensor in sensores or []}
        self.usuarios: dict[int, Usuario] = {}
        self.agregados: list[object] = []
        self.commits = 0
        self.siguiente_alerta = 1

    def get(self, modelo: object, ident: object, **_kwargs: object) -> object | None:
        if modelo is Camara:
            return self.camaras.get(ident)  # type: ignore[arg-type]
        if modelo is Usuario:
            return self.usuarios.get(ident)  # type: ignore[arg-type]
        return None

    def scalar(self, sentencia: object) -> object | None:
        if "FROM sensores" in str(sentencia):
            params = sentencia.compile().params  # type: ignore[attr-defined]
            camara_id = params.get("camara_id_1")
            return next(
                (
                    sensor
                    for sensor in self.sensores.values()
                    if sensor.camara_id == camara_id and sensor.activo
                ),
                None,
            )
        return None

    def add(self, fila: object) -> None:
        if isinstance(fila, AlertaSeguridad) and fila.id is None:
            fila.id = self.siguiente_alerta
            self.siguiente_alerta += 1
        self.agregados.append(fila)

    def commit(self) -> None:
        self.commits += 1


def _camara(
    camara_id: int,
    rango_min_c: float = 0.0,
    rango_max_c: float = 4.0,
    es_demo: bool = True,
    min_para_riesgo: int = 10,
) -> Camara:
    return Camara(
        id=camara_id,
        restaurante_id=RESTAURANTE_DEMO_ID,
        es_demo=es_demo,
        nombre=f"Cámara {camara_id}",
        rango_min_c=rango_min_c,
        rango_max_c=rango_max_c,
        min_para_riesgo=min_para_riesgo,
        min_para_merma=60,
        estado="en_rango",
    )


def _sensor(sensor_id: str, camara_id: int, activo: bool = True) -> Sensor:
    return Sensor(
        id=sensor_id,
        camara_id=camara_id,
        token_hash="hash",
        activo=activo,
    )


def _cliente(sesion: SesionFalsa, restaurante_id: int | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    if restaurante_id is not None:
        app.dependency_overrides[get_restaurante_id] = lambda: restaurante_id
    return TestClient(app)


def _cliente_con_auth(
    monkeypatch: pytest.MonkeyPatch,
    sesion: SesionFalsa,
    usuario: Usuario,
) -> tuple[TestClient, dict[str, str]]:
    monkeypatch.setenv("AUTH_REQUERIDA", "1")
    limpiar_cache_settings()
    sesion.usuarios[usuario.id] = usuario
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    app.dependency_overrides[sesion_si_auth] = lambda: sesion
    return TestClient(app), {"Authorization": f"Bearer {crear_token(usuario)}"}


def _limpiar_activas() -> None:
    with demo_mod._cerrojo:
        for simulacion in demo_mod._activas.values():
            simulacion.cancelar.set()
            simulacion.terminada.set()
        demo_mod._activas.clear()


@pytest.fixture(autouse=True)
def _entorno_demo(monkeypatch):
    """Demo encendida y registro de simulaciones limpio en cada prueba."""
    monkeypatch.setenv("DEMO_HABILITADA", "1")
    monkeypatch.setenv("ENTORNO", "local")
    monkeypatch.delenv("RENDER", raising=False)
    limpiar_cache_settings()
    _limpiar_activas()
    yield
    _limpiar_activas()
    limpiar_cache_settings()


def _sesion_basica() -> SesionFalsa:
    return SesionFalsa(
        camaras=[
            _camara(1, rango_min_c=0.0, rango_max_c=2.0),
            _camara(4, rango_min_c=4.0, rango_max_c=8.0),
            _camara(5, rango_min_c=-22.0, rango_max_c=-18.0),
            _camara(6, es_demo=False),
        ],
        sensores=[
            _sensor("S-PES-01", 1),
            _sensor("S-VER-01", 4),
            _sensor("S-CON-01", 5),
            _sensor("S-API-06", 6),
        ],
    )


# --- Gate y roles -----------------------------------------------------------


def test_demo_apagada_regresa_404_sin_registrar_la_ruta(monkeypatch):
    """Con el flag apagado la ruta no existe: 404 aunque no haya token."""
    monkeypatch.setenv("DEMO_HABILITADA", "0")
    monkeypatch.setenv("AUTH_REQUERIDA", "1")
    limpiar_cache_settings()

    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/ataque")

    assert respuesta.status_code == 404


def test_otro_tenant_regresa_404():
    with _cliente(_sesion_basica(), restaurante_id=2) as cliente:
        respuesta = cliente.post("/api/demo/ataque")

    assert respuesta.status_code == 404


def test_gerente_regresa_403(monkeypatch):
    usuario = Usuario(
        id=8,
        restaurante_id=RESTAURANTE_DEMO_ID,
        usuario="gerente",
        password_hash="hash",
        rol="gerente",
    )
    cliente, headers = _cliente_con_auth(monkeypatch, _sesion_basica(), usuario)

    with cliente:
        respuesta = cliente.post("/api/demo/ataque", headers=headers)

    assert respuesta.status_code == 403
    assert "dueno o jefe_cocina" in respuesta.json()["detail"]


@pytest.mark.parametrize("rol", ["dueno", "jefe_cocina"])
def test_dueno_y_jefe_pueden_usar_la_demo(monkeypatch, rol):
    usuario = Usuario(
        id=9,
        restaurante_id=RESTAURANTE_DEMO_ID,
        usuario=f"usuario-{rol}",
        password_hash="hash",
        rol=rol,
    )
    cliente, headers = _cliente_con_auth(monkeypatch, _sesion_basica(), usuario)

    with cliente:
        respuesta = cliente.post("/api/demo/ataque", headers=headers)

    assert respuesta.status_code == 201


def test_usuario_de_otro_tenant_regresa_404(monkeypatch):
    usuario = Usuario(
        id=7,
        restaurante_id=2,
        usuario="ajeno",
        password_hash="hash",
        rol="dueno",
    )
    cliente, headers = _cliente_con_auth(monkeypatch, _sesion_basica(), usuario)

    with cliente:
        respuesta = cliente.post("/api/demo/ataque", headers=headers)

    assert respuesta.status_code == 404


# --- Falla, puerta y recuperación ------------------------------------------


def test_falla_programa_la_tarea_con_temperaturas_del_rango(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(demo_mod, "_simular_falla", lambda *args: llamadas.append(args))

    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/falla", json={"camara_id": 1})

    assert respuesta.status_code == 202
    assert respuesta.json() == {
        "mensaje": "Falla de compresor en curso.",
        "camara_id": 1,
    }
    camara_id, sensor_id, base, paso, min_para_riesgo, cancelar = llamadas[0]
    assert (camara_id, sensor_id, min_para_riesgo) == (1, "S-PES-01", 10)
    assert base == pytest.approx(1.8)
    assert paso == pytest.approx(0.4)
    assert isinstance(cancelar, threading.Event)
    assert "falla" not in demo_mod._activas


def test_falla_usa_la_camara_1_por_defecto(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(demo_mod, "_simular_falla", lambda *args: llamadas.append(args))

    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/falla")

    assert respuesta.status_code == 202
    assert respuesta.json()["camara_id"] == 1
    assert llamadas[0][0:2] == (1, "S-PES-01")


@pytest.mark.parametrize(
    ("camara_id", "base", "paso", "rango_max", "min_para_riesgo", "sensor_id"),
    [
        (4, 7.8, 0.8, 8.0, 30, "S-VER-01"),
        (5, -18.2, 0.8, -18.0, 20, "S-CON-01"),
    ],
    ids=["camara-4", "camara-5"],
)
def test_falla_calcula_temperaturas_para_camaras_4_y_5(
    monkeypatch, camara_id, base, paso, rango_max, min_para_riesgo, sensor_id
):
    if camara_id == 4:
        sesion = SesionFalsa(
            camaras=[_camara(4, rango_min_c=4.0, rango_max_c=8.0, min_para_riesgo=30)],
            sensores=[_sensor("S-VER-01", 4)],
        )
    else:
        sesion = SesionFalsa(
            camaras=[
                _camara(5, rango_min_c=-22.0, rango_max_c=-18.0, min_para_riesgo=20)
            ],
            sensores=[_sensor("S-CON-01", 5)],
        )
    llamadas: list[tuple] = []
    monkeypatch.setattr(demo_mod, "_simular_falla", lambda *args: llamadas.append(args))

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/demo/falla", json={"camara_id": camara_id})

    assert respuesta.status_code == 202
    _, sensor, base_real, paso_real, riesgo_real, _ = llamadas[0]
    assert sensor == sensor_id
    assert base_real == pytest.approx(base)
    assert paso_real == pytest.approx(paso)
    assert riesgo_real == min_para_riesgo
    # La segunda lectura cruza el máximo del rango.
    assert base_real < rango_max < base_real + paso_real


def test_puerta_usa_la_camara_5_por_defecto_con_el_centro_del_rango(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(demo_mod, "_simular_puerta", lambda *args: llamadas.append(args))

    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/puerta")

    assert respuesta.status_code == 202
    assert respuesta.json()["camara_id"] == 5
    camara_id, sensor_id, base, paso, cancelar = llamadas[0]
    assert (camara_id, sensor_id) == (5, "S-CON-01")
    assert base == pytest.approx(-20.0)
    assert paso == pytest.approx(0.2)
    assert isinstance(cancelar, threading.Event)


def test_puerta_en_camara_1_no_usa_la_temperatura_del_congelador(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(demo_mod, "_simular_puerta", lambda *args: llamadas.append(args))

    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/puerta", json={"camara_id": 1})

    assert respuesta.status_code == 202
    assert llamadas[0][2] == pytest.approx(1.0)
    assert llamadas[0][3] == pytest.approx(1.0 / 9)


def test_puerta_sube_la_temperatura_sin_salir_del_rango(monkeypatch):
    """La secuencia es creciente, la última queda bajo el máximo y la puerta va abierta."""
    lecturas: list[tuple[float, bool]] = []

    class EventoSinEspera:
        def is_set(self) -> bool:
            return False

        def wait(self, timeout: float | None = None) -> bool:
            return False

    def enviar(_camara_id, _sensor_id, temperatura, puerta_abierta):
        lecturas.append((temperatura, puerta_abierta))
        return "alerta", False

    monkeypatch.setattr(demo_mod, "_enviar_lectura", enviar)
    demo_mod._simular_puerta(
        5, "S-CON-01", -20.0, 0.2, EventoSinEspera()  # type: ignore[arg-type]
    )

    temperaturas = [temperatura for temperatura, _ in lecturas]
    assert len(temperaturas) == demo_mod.LECTURAS_PUERTA
    assert temperaturas == sorted(temperaturas)
    assert temperaturas[-1] < -18.0
    assert all(puerta_abierta for _, puerta_abierta in lecturas)


def test_recuperar_programa_la_tarea_y_responde_202(monkeypatch):
    llamadas: list[bool] = []
    monkeypatch.setattr(demo_mod, "_simular_recuperacion", lambda: llamadas.append(True))

    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/recuperar")

    assert respuesta.status_code == 202
    assert llamadas == [True]
    assert "recuperar" not in demo_mod._activas


def test_falla_con_camara_inexistente_regresa_404():
    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/falla", json={"camara_id": 99})

    assert respuesta.status_code == 404


def test_falla_con_camara_creada_por_api_regresa_409():
    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/falla", json={"camara_id": 6})

    assert respuesta.status_code == 409
    assert "no es de la demo" in respuesta.json()["detail"]


def test_falla_sin_sensor_regresa_409():
    sesion = SesionFalsa(camaras=[_camara(1)], sensores=[])

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/demo/falla")

    assert respuesta.status_code == 409
    assert "sensor activo" in respuesta.json()["detail"]


def test_camara_id_invalido_regresa_422():
    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/falla", json={"camara_id": 0})

    assert respuesta.status_code == 422


def test_clicks_repetidos_regresan_409(monkeypatch):
    monkeypatch.setattr(demo_mod, "_simular_falla", lambda *_args: None)
    demo_mod._reservar("falla")

    with _cliente(_sesion_basica()) as cliente:
        respuesta = cliente.post("/api/demo/falla")

    assert respuesta.status_code == 409
    assert "simulación de falla" in respuesta.json()["detail"]


def test_la_reserva_se_libera_al_terminar(monkeypatch):
    monkeypatch.setattr(demo_mod, "_simular_falla", lambda *_args: None)

    with _cliente(_sesion_basica()) as cliente:
        primera = cliente.post("/api/demo/falla")
        segunda = cliente.post("/api/demo/falla")

    assert primera.status_code == 202
    assert segunda.status_code == 202
    assert "falla" not in demo_mod._activas


def test_el_slot_vencido_se_libera():
    simulacion = demo_mod._reservar("falla")
    with demo_mod._cerrojo:
        simulacion.iniciada_en = time.monotonic() - demo_mod.EXPIRACION_SIMULACION_S - 1

    nueva = demo_mod._reservar("falla")

    assert nueva is not simulacion
    assert simulacion.cancelar.is_set()
    assert simulacion.terminada.is_set()


def test_la_falla_se_detiene_al_cancelar(monkeypatch):
    class EventoFalso:
        def __init__(self) -> None:
            self.activo = False

        def is_set(self) -> bool:
            return self.activo

        def set(self) -> None:
            self.activo = True

        def wait(self, timeout: float | None = None) -> bool:
            return self.activo

    cancelar = EventoFalso()
    enviadas: list[float] = []

    def enviar(_camara_id, _sensor_id, temperatura, _puerta):
        enviadas.append(temperatura)
        cancelar.set()
        return "alerta", False

    monkeypatch.setattr(demo_mod, "_enviar_lectura", enviar)
    demo_mod._simular_falla(1, "S-PES-01", 1.8, 0.4, 10, cancelar)  # type: ignore[arg-type]

    assert enviadas == [1.8]


def test_recuperar_espera_a_que_la_simulacion_cancele():
    simulacion = demo_mod._reservar("falla")

    def tarea() -> None:
        simulacion.cancelar.wait(timeout=1)
        simulacion.terminada.set()

    hilo = threading.Thread(target=tarea)
    hilo.start()
    demo_mod._cancelar_simulaciones()
    hilo.join(timeout=1)

    assert simulacion.cancelar.is_set()
    assert not hilo.is_alive()


# --- Ataque SIEM ------------------------------------------------------------


def test_ataque_inserta_una_alerta_simulada_y_regresa_201():
    sesion = _sesion_basica()

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/demo/ataque")

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["regla_id"] == "3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41"
    assert cuerpo["regla"] == "Fuerza bruta de credenciales en la API"
    assert cuerpo["severidad"] == "high"
    assert cuerpo["ip_origen"] == "203.0.113.66"
    assert cuerpo["accion"] == "bloquear_ip"
    assert cuerpo["detalle"]["simulado"] is True
    assert cuerpo["detalle"]["clave"] == "ip:203.0.113.66"
    assert cuerpo["detalle"]["intentos"] >= 10
    assert set(cuerpo["detalle"]["rutas"]) == {"/api/auth/login", "/api/telemetria"}

    assert len(sesion.agregados) == 1
    assert isinstance(sesion.agregados[0], AlertaSeguridad)
    assert not any(isinstance(fila, IpBloqueada) for fila in sesion.agregados)


# --- Seed -------------------------------------------------------------------


def test_el_seed_incluye_al_dueno_demo():
    _, _, _, usuarios = construir_seed(sensor_tokens=TOKENS, password="demo")

    dueno = next(usuario for usuario in usuarios if usuario.usuario == "dueno")
    assert dueno.rol == "dueno"
    assert dueno.restaurante_id == RESTAURANTE_DEMO_ID
