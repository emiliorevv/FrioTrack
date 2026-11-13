"""Pruebas del middleware de logs de acceso y bloqueo de IPs."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.db.models import IpBloqueada, LogAcceso
from app.db.session import get_db
from app.main import create_app
from app.middleware import acceso
from app.middleware.acceso import AccesoLogMiddleware, ip_de_scope, ruta_de_scope
from app.routers import telemetria as router_telemetria


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


def _app_de_prueba() -> FastAPI:
    app = FastAPI()

    @app.get("/api/salud")
    def salud() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/simulador/tick")
    def tick() -> dict[str, int]:
        return {"lecturas": 0}

    app.add_middleware(AccesoLogMiddleware)
    return app


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


class TestHelpers:
    def test_ip_usa_el_ultimo_x_forwarded_for(self):
        scope = _scope(
            headers=[(b"x-forwarded-for", b"1.2.3.4, 198.51.100.7, 187.190.12.4")]
        )

        assert ip_de_scope(scope) == "187.190.12.4"

    def test_ip_sin_cabecera_usa_la_conexion_directa(self):
        assert ip_de_scope(_scope()) == "203.0.113.9"

    def test_ip_sin_conexion_devuelve_cadena_vacia(self):
        assert ip_de_scope(_scope(client=None)) == ""

    def test_ruta_no_incluye_query_string(self):
        scope = _scope(
            path="/api/stream",
            query_string=b"token=jwt-que-no-se-guarda",
        )

        assert ruta_de_scope(scope) == "/api/stream"


def test_ip_bloqueada_responde_403_y_registra(monkeypatch, sesion_falsa, capsys):
    _activar_db(monkeypatch)
    sesion_falsa.bloqueada = IpBloqueada(
        ip="9.9.9.9",
        hasta=datetime.now(UTC) + timedelta(hours=1),
        motivo="regla-demo",
    )

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get(
            "/api/salud",
            headers={"X-Forwarded-For": "1.1.1.1, 9.9.9.9", "User-Agent": "prueba-siem"},
        )

    assert respuesta.status_code == 403
    assert "bloqueada" in respuesta.json()["detail"]
    # Solo se consultó la tabla de bloqueos: la ruta nunca se ejecutó.
    assert sesion_falsa.consultas == [(IpBloqueada, "9.9.9.9")]
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.ip_origen == "9.9.9.9"
    assert fila.metodo == "GET"
    assert fila.ruta == "/api/salud"
    assert fila.status == 403
    assert fila.credencial == "ninguna"
    assert fila.sujeto is None
    assert fila.user_agent == "prueba-siem"

    salida = _lineas(capsys.readouterr().out)[-1]
    assert salida["ip_origen"] == "9.9.9.9"
    assert salida["status"] == 403
    assert salida["latencia_ms"] >= 0


def test_ip_no_bloqueada_pasa_y_registra(monkeypatch, sesion_falsa, capsys):
    _activar_db(monkeypatch)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get(
            "/api/salud?token=no-se-guarda", headers={"User-Agent": "navegador-demo"}
        )

    assert respuesta.status_code == 200
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.ip_origen == "testclient"
    assert fila.ruta == "/api/salud"
    assert fila.status == 200
    assert fila.credencial == "ninguna"
    assert fila.sujeto is None
    assert fila.user_agent == "navegador-demo"

    salida = _lineas(capsys.readouterr().out)[-1]
    assert salida["ruta"] == "/api/salud"
    assert salida["status"] == 200
    assert salida["metodo"] == "GET"


def test_ruta_de_cron_usa_credencial_cron(monkeypatch, sesion_falsa):
    _activar_db(monkeypatch)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.post("/api/simulador/tick")

    assert respuesta.status_code == 200
    assert sesion_falsa.insertados[0].credencial == "cron"
    assert sesion_falsa.insertados[0].sujeto is None


def test_telemetria_registra_credencial_sensor_y_sujeto(monkeypatch, sesion_falsa, capsys):
    _activar_db(monkeypatch)
    monkeypatch.setattr(
        router_telemetria,
        "procesar_telemetria",
        lambda _session, _datos, token: (18342, "en_rango"),
    )
    app = create_app()

    def sesion_sin_base():
        yield None

    app.dependency_overrides[get_db] = sesion_sin_base

    with TestClient(app) as cliente:
        respuesta = cliente.post(
            "/api/telemetria",
            json=_payload(),
            headers={
                "Authorization": "Bearer token-de-prueba",
                "X-Forwarded-For": "10.0.0.5",
            },
        )

    assert respuesta.status_code == 202
    assert len(sesion_falsa.insertados) == 1
    fila = sesion_falsa.insertados[0]
    assert fila.ip_origen == "10.0.0.5"
    assert fila.ruta == "/api/telemetria"
    assert fila.status == 202
    assert fila.credencial == "sensor"
    assert fila.sujeto == "S-PES-01"
    assert fila.latencia_ms >= 0

    salida = _lineas(capsys.readouterr().out)[-1]
    assert salida["status"] == 202
    assert salida["credencial"] == "sensor"
    assert salida["sujeto"] == "S-PES-01"
    assert isinstance(salida["latencia_ms"], int)


def test_flag_apagada_solo_escribe_stdout(monkeypatch, capsys):
    monkeypatch.setenv("MIDDLEWARE_ACCESO_DB", "0")
    limpiar_cache_settings()

    def explotar(*_args, **_kwargs):
        raise AssertionError("con MIDDLEWARE_ACCESO_DB=0 no debe tocar la base")

    monkeypatch.setattr(acceso, "SessionLocal", explotar)
    monkeypatch.setattr(acceso, "get_engine", explotar)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get("/api/salud")

    assert respuesta.status_code == 200
    salida = _lineas(capsys.readouterr().out)[-1]
    assert salida["status"] == 200
    assert salida["ruta"] == "/api/salud"


def test_fallo_de_base_no_bloquea_la_peticion(monkeypatch, capsys):
    _activar_db(monkeypatch)

    def sin_base(*_args, **_kwargs):
        raise RuntimeError("base caída")

    monkeypatch.setattr(acceso, "SessionLocal", sin_base)
    monkeypatch.setattr(acceso, "get_engine", sin_base)

    with TestClient(_app_de_prueba()) as cliente:
        respuesta = cliente.get("/api/salud")

    assert respuesta.status_code == 200
    salida = _lineas(capsys.readouterr().out)[-1]
    assert salida["status"] == 200
