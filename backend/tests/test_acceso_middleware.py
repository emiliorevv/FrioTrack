"""Pruebas del middleware de logs de acceso y bloqueo de IPs."""

import json
import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.db.models import IpBloqueada, LogAcceso
from app.db.session import get_db
from app.main import create_app
from app.middleware import acceso
from app.middleware.acceso import AccesoLogMiddleware, ip_de_scope, ruta_de_scope
from app.routers import telemetria as router_telemetria

IP_CLIENTE = "testclient"


class SesionFalsa:
    """Sesión mínima que registra consultas e inserciones sin tocar la base."""

    def __init__(self, bloqueada: IpBloqueada | None = None) -> None:
        self.bloqueada = bloqueada
        self.consultas: list[tuple[object, object]] = []
        self.insertados: list[LogAcceso] = []
        self.commits = 0

    def get(self, modelo: object, ident: object) -> object | None:
        self.consultas.append((modelo, ident))
        return self.bloqueada if modelo is IpBloqueada else None

    def add(self, fila: LogAcceso) -> None:
        self.insertados.append(fila)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        pass


@pytest.fixture
def sesion_falsa(monkeypatch):
    """Sustituye la fábrica de sesiones del middleware por una en memoria."""
    sesion = SesionFalsa()
    monkeypatch.setattr(acceso, "SessionLocal", lambda bind=None: sesion)
    monkeypatch.setattr(acceso, "get_engine", lambda: None)
    return sesion


def _activar_db(monkeypatch):
    monkeypatch.setenv("MIDDLEWARE_ACCESO_DB", "1")
    limpiar_cache_settings()


def _configurar_entorno(monkeypatch, *, entorno: str, render: str | None = None) -> None:
    monkeypatch.setenv("ENTORNO", entorno)
    if render is None:
        monkeypatch.delenv("RENDER", raising=False)
    else:
        monkeypatch.setenv("RENDER", render)
    limpiar_cache_settings()


def _app_de_prueba() -> FastAPI:
    app = FastAPI()

    @app.get("/api/salud")
    def salud() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/simulador/tick")
    def tick() -> dict[str, int]:
        return {"lecturas": 0}

    @app.get("/api/explotar")
    def explotar(request: Request) -> dict[str, bool]:
        request.state.credencial = "usuario"
        request.state.sujeto = "jefe-demo"
        raise RuntimeError("fallo de la ruta")

    app.add_middleware(AccesoLogMiddleware)
    return app


def _esperar_registros(cliente: TestClient) -> None:
    """Espera el INSERT agendado; sin esto la prueba leería la sesión antes."""
    cliente.portal.call(acceso.esperar_registros)


def _lineas(capturada: str) -> list[dict]:
    return [json.loads(linea) for linea in capturada.splitlines() if linea.strip()]


def _payload() -> dict[str, object]:
    return {
        "sensor_id": "S-PES-01",
        "camara_id": 1,
        "ts": "2026-11-18T13:05:00-06:00",
        "temperatura_c": 1.4,
        "humedad_pct": 88,
        "puerta_abierta": False,
    }


def _scope(headers: list[tuple[bytes, bytes]] | None = None, **cambios) -> dict:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/salud",
        "headers": headers or [],
        "client": ("203.0.113.9", 1234),
    }
    scope.update(cambios)
    return scope


def _bloquear(sesion: SesionFalsa, ip: str = IP_CLIENTE) -> None:
    sesion.bloqueada = IpBloqueada(
        ip=ip,
        hasta=datetime.now(UTC) + timedelta(hours=1),
        motivo="regla-demo",
    )


def _app_telemetria(monkeypatch) -> FastAPI:
    monkeypatch.setattr(
        router_telemetria,
        "procesar_telemetria",
        lambda _session, _datos, token: (18342, "en_rango"),
    )
    app = create_app()

    def sesion_sin_base():
        yield None

    app.dependency_overrides[get_db] = sesion_sin_base
    return app


class TestHelpers:
    def test_ip_ignora_x_forwarded_for_en_local(self, monkeypatch):
        _configurar_entorno(monkeypatch, entorno="local")
        scope = _scope(headers=[(b"x-forwarded-for", b"1.2.3.4, 187.190.12.4")])

        assert ip_de_scope(scope) == "203.0.113.9"

    def test_ip_usa_el_ultimo_x_forwarded_for_en_produccion(self, monkeypatch):
        _configurar_entorno(monkeypatch, entorno="produccion")
        scope = _scope(
            headers=[(b"x-forwarded-for", b"1.2.3.4, 198.51.100.7, 187.190.12.4")]
        )

        assert ip_de_scope(scope) == "187.190.12.4"

    def test_ip_usa_x_forwarded_for_si_render_marca_produccion(self, monkeypatch):
        _configurar_entorno(monkeypatch, entorno="local", render="true")
        scope = _scope(headers=[(b"x-forwarded-for", b"1.2.3.4, 187.190.12.4")])

        assert ip_de_scope(scope) == "187.190.12.4"

    def test_ip_sin_cabecera_usa_la_conexion_directa(self, monkeypatch):
        _configurar_entorno(monkeypatch, entorno="produccion")

        assert ip_de_scope(_scope()) == "203.0.113.9"

    def test_ip_sin_conexion_devuelve_cadena_vacia(self, monkeypatch):
        _configurar_entorno(monkeypatch, entorno="local")

        assert ip_de_scope(_scope(client=None)) == ""

    def test_ruta_no_incluye_query_string(self):
        scope = _scope(
            path="/api/stream",
            query_string=b"token=jwt-que-no-se-guarda",
        )

        assert ruta_de_scope(scope) == "/api/stream"


def test_ip_bloqueada_responde_403_y_registra(monkeypatch, sesion_falsa, log_stdout):
    _activar_db(monkeypatch)
    _configurar_entorno(monkeypatch, entorno="local")
    _bloquear(sesion_falsa)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get(
            "/api/salud",
            headers={"X-Forwarded-For": "1.1.1.1, 9.9.9.9", "User-Agent": "prueba-siem"},
        )
        _esperar_registros(cliente)

    assert respuesta.status_code == 403
    assert "bloqueada" in respuesta.json()["detail"]
    # La IP sale de la conexión, no del XFF falsificado en local.
    assert sesion_falsa.consultas == [(IpBloqueada, IP_CLIENTE)]
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.ip_origen == IP_CLIENTE
    assert fila.metodo == "GET"
    assert fila.ruta == "/api/salud"
    assert fila.status == 403
    assert fila.credencial == "ninguna"
    assert fila.sujeto is None
    assert fila.user_agent == "prueba-siem"

    salida = _lineas(log_stdout.getvalue())[-1]
    assert salida["ip_origen"] == IP_CLIENTE
    assert salida["status"] == 403
    assert salida["latencia_ms"] >= 0


def test_ip_no_bloqueada_pasa_y_registra(monkeypatch, sesion_falsa, log_stdout):
    _activar_db(monkeypatch)
    _configurar_entorno(monkeypatch, entorno="local")

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get(
            "/api/salud?token=no-se-guarda",
            headers={"User-Agent": "navegador-demo", "X-Forwarded-For": "1.2.3.4"},
        )
        _esperar_registros(cliente)

    assert respuesta.status_code == 200
    assert sesion_falsa.consultas == [(IpBloqueada, IP_CLIENTE)]
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.ip_origen == IP_CLIENTE
    assert fila.ruta == "/api/salud"
    assert fila.status == 200
    assert fila.credencial == "ninguna"
    assert fila.sujeto is None
    assert fila.user_agent == "navegador-demo"

    salida = _lineas(log_stdout.getvalue())[-1]
    assert salida["ruta"] == "/api/salud"
    assert salida["status"] == 200
    assert salida["metodo"] == "GET"


def test_cache_de_bloqueos_evita_consultas_repetidas(monkeypatch, sesion_falsa):
    _activar_db(monkeypatch)
    _configurar_entorno(monkeypatch, entorno="local")
    _bloquear(sesion_falsa)

    with TestClient(_app_de_prueba()) as cliente:
        primera = cliente.get("/api/salud")
        _esperar_registros(cliente)
        segunda = cliente.get("/api/salud")
        _esperar_registros(cliente)

    assert primera.status_code == 403
    assert segunda.status_code == 403
    assert sesion_falsa.consultas == [(IpBloqueada, IP_CLIENTE)]
    assert len(sesion_falsa.insertados) == 2


def test_cache_de_bloqueos_expira(monkeypatch, sesion_falsa):
    _activar_db(monkeypatch)
    _configurar_entorno(monkeypatch, entorno="local")
    monkeypatch.setattr(acceso, "TTL_BLOQUEO_SEG", 0.0)

    with TestClient(_app_de_prueba()) as cliente:
        cliente.get("/api/salud")
        _esperar_registros(cliente)
        cliente.get("/api/salud")
        _esperar_registros(cliente)

    assert sesion_falsa.consultas == [(IpBloqueada, IP_CLIENTE), (IpBloqueada, IP_CLIENTE)]


def test_ruta_de_cron_usa_credencial_cron(monkeypatch, sesion_falsa):
    _activar_db(monkeypatch)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.post("/api/simulador/tick")
        _esperar_registros(cliente)

    assert respuesta.status_code == 200
    assert sesion_falsa.insertados[0].credencial == "cron"
    assert sesion_falsa.insertados[0].sujeto is None


def test_telemetria_registra_credencial_sensor_y_sujeto(monkeypatch, sesion_falsa, log_stdout):
    _activar_db(monkeypatch)
    app = _app_telemetria(monkeypatch)

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/telemetria",
            json=_payload(),
            headers={"Authorization": "Bearer token-de-prueba"},
        )
        _esperar_registros(cliente)

    assert respuesta.status_code == 202
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.ip_origen == IP_CLIENTE
    assert fila.ruta == "/api/telemetria"
    assert fila.status == 202
    assert fila.credencial == "sensor"
    assert fila.sujeto == "S-PES-01"
    assert fila.latencia_ms >= 0

    salida = _lineas(log_stdout.getvalue())[-1]
    assert salida["status"] == 202
    assert salida["credencial"] == "sensor"
    assert salida["sujeto"] == "S-PES-01"
    assert isinstance(salida["latencia_ms"], int)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Token raro"},
        {"Authorization": "Bearer   "},
    ],
)
def test_telemetria_401_conserva_credencial_y_sujeto(
    monkeypatch, sesion_falsa, log_stdout, headers
):
    _activar_db(monkeypatch)
    app = _app_telemetria(monkeypatch)

    with TestClient(app) as cliente:
        respuesta = cliente.post("/api/telemetria", json=_payload(), headers=headers)
        _esperar_registros(cliente)

    assert respuesta.status_code == 401
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.status == 401
    assert fila.credencial == "sensor"
    assert fila.sujeto == "S-PES-01"

    salida = _lineas(log_stdout.getvalue())[-1]
    assert salida["status"] == 401
    assert salida["credencial"] == "sensor"
    assert salida["sujeto"] == "S-PES-01"


def test_ruta_que_lanza_registra_500_y_responde_500(monkeypatch, sesion_falsa, log_stdout):
    _activar_db(monkeypatch)

    with TestClient(_app_de_prueba(), raise_server_exceptions=False) as cliente:
        respuesta = cliente.get("/api/explotar")
        _esperar_registros(cliente)

    assert respuesta.status_code == 500
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.status == 500
    assert fila.ruta == "/api/explotar"
    assert fila.credencial == "usuario"
    assert fila.sujeto == "jefe-demo"

    salida = _lineas(log_stdout.getvalue())[-1]
    assert salida["status"] == 500
    assert salida["ruta"] == "/api/explotar"
    assert salida["credencial"] == "usuario"
    assert salida["sujeto"] == "jefe-demo"


def test_la_respuesta_no_espera_al_insert(monkeypatch, sesion_falsa):
    """Los headers salen aunque el INSERT siga bloqueado en el threadpool."""
    _activar_db(monkeypatch)
    _configurar_entorno(monkeypatch, entorno="local")
    llamado = threading.Event()
    liberar = threading.Event()

    def insertar_lento(_datos):
        llamado.set()
        liberar.wait(timeout=5)

    monkeypatch.setattr(acceso, "_insertar_log", insertar_lento)

    with TestClient(_app_de_prueba()) as cliente:
        try:
            respuesta = cliente.get("/api/salud")
            assert respuesta.status_code == 200
            assert llamado.wait(timeout=5)
        finally:
            liberar.set()
        _esperar_registros(cliente)


def test_403_incluye_cors_comodin(monkeypatch, sesion_falsa):
    _activar_db(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    limpiar_cache_settings()
    _bloquear(sesion_falsa)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get(
            "/api/salud", headers={"Origin": "https://panel.example"}
        )
        _esperar_registros(cliente)

    assert respuesta.status_code == 403
    assert respuesta.headers["access-control-allow-origin"] == "*"


def test_403_incluye_cors_solo_si_el_origen_esta_en_la_lista(monkeypatch, sesion_falsa):
    _activar_db(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "https://panel.example, https://otro.example")
    limpiar_cache_settings()
    _bloquear(sesion_falsa)

    with TestClient(_app_de_prueba()) as cliente:
        permitido = cliente.get(
            "/api/salud", headers={"Origin": "https://panel.example"}
        )
        _esperar_registros(cliente)
        ajeno = cliente.get("/api/salud", headers={"Origin": "https://malo.example"})
        _esperar_registros(cliente)

    assert permitido.status_code == 403
    assert permitido.headers["access-control-allow-origin"] == "https://panel.example"
    assert permitido.headers["vary"] == "Origin"
    assert ajeno.status_code == 403
    assert "access-control-allow-origin" not in ajeno.headers


def test_flag_apagada_solo_escribe_stdout(monkeypatch, log_stdout):
    monkeypatch.setenv("MIDDLEWARE_ACCESO_DB", "0")
    limpiar_cache_settings()

    def explotar(*_args, **_kwargs):
        raise AssertionError("con MIDDLEWARE_ACCESO_DB=0 no debe tocar la base")

    monkeypatch.setattr(acceso, "SessionLocal", explotar)
    monkeypatch.setattr(acceso, "get_engine", explotar)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get("/api/salud")

    assert respuesta.status_code == 200
    salida = _lineas(log_stdout.getvalue())[-1]
    assert salida["status"] == 200
    assert salida["ruta"] == "/api/salud"


def test_fallo_de_base_no_bloquea_la_peticion(monkeypatch, log_stdout):
    _activar_db(monkeypatch)
    _configurar_entorno(monkeypatch, entorno="local")

    def sin_base(*_args, **_kwargs):
        raise RuntimeError("base caída")

    monkeypatch.setattr(acceso, "SessionLocal", sin_base)
    monkeypatch.setattr(acceso, "get_engine", sin_base)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get("/api/salud")
        _esperar_registros(cliente)

    assert respuesta.status_code == 200
    salida = _lineas(log_stdout.getvalue())[-1]
    assert salida["status"] == 200


def test_avisar_fallo_loguea_y_rate_limita(monkeypatch):
    llamadas: list[tuple] = []
    monkeypatch.setattr(acceso.logger, "warning", lambda *args, **kwargs: llamadas.append(args))

    error = RuntimeError("base caída")
    acceso._avisar_fallo("ips_bloqueadas", error)
    acceso._avisar_fallo("ips_bloqueadas", error)  # mismo minuto: no duplica
    acceso._avisar_fallo("logs_acceso", error)

    assert len(llamadas) == 2
    assert llamadas[0][1] == "ips_bloqueadas"
    assert llamadas[1][1] == "logs_acceso"
