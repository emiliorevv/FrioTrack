"""Pruebas de la validación de configuración en producción."""

import json

import pytest
from pydantic import ValidationError

from app.config import (
    JWT_SECRET_POR_DEFECTO,
    SENSORES_ESPERADOS,
    get_settings,
    leer_sensor_tokens,
    limpiar_cache_settings,
)
from app.main import create_app

SECRETO_FUERTE = "secreto-de-produccion-con-32-o-mas-caracteres"
TOKENS_VALIDOS = {sensor_id: f"token-{sensor_id.lower()}" for sensor_id in SENSORES_ESPERADOS}


@pytest.fixture(autouse=True)
def _sin_cache_settings(monkeypatch):
    """Cada prueba lee el entorno que monkeypatch acaba de definir."""
    monkeypatch.delenv("RENDER", raising=False)
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def _configurar_produccion(monkeypatch, entorno: str | None = "produccion", **valores):
    """Deja una configuración de producción completa y aplica los cambios pedidos."""
    if entorno is None:
        monkeypatch.delenv("ENTORNO", raising=False)
    else:
        monkeypatch.setenv("ENTORNO", entorno)
    completa = {
        "JWT_SECRET": SECRETO_FUERTE,
        "CRON_TOKEN": "cron-de-produccion",
        "SEED_PASSWORD": "no-es-la-demo",
        "SENSOR_TOKENS": json.dumps(TOKENS_VALIDOS),
    }
    completa.update(valores)
    for nombre, valor in completa.items():
        monkeypatch.setenv(nombre, valor)


def test_local_con_secreto_por_defecto_no_lanza(monkeypatch):
    monkeypatch.setenv("ENTORNO", "local")
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET_POR_DEFECTO)

    get_settings().validar_configuracion()  # no debe lanzar


def test_produccion_con_secreto_por_defecto_lanza(monkeypatch):
    _configurar_produccion(monkeypatch, JWT_SECRET=JWT_SECRET_POR_DEFECTO)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings().validar_configuracion()


def test_produccion_con_secreto_corto_lanza(monkeypatch):
    _configurar_produccion(monkeypatch, JWT_SECRET="corto")

    with pytest.raises(RuntimeError, match="32 caracteres"):
        get_settings().validar_configuracion()


@pytest.mark.parametrize("cron_token", ["", "   "], ids=["vacio", "en-blanco"])
def test_produccion_sin_cron_token_lanza(monkeypatch, cron_token):
    _configurar_produccion(monkeypatch, CRON_TOKEN=cron_token)

    with pytest.raises(RuntimeError, match="CRON_TOKEN"):
        get_settings().validar_configuracion()


def test_produccion_con_password_de_seed_demo_lanza(monkeypatch):
    _configurar_produccion(monkeypatch, SEED_PASSWORD="friotrack-demo")

    with pytest.raises(RuntimeError, match="SEED_PASSWORD"):
        get_settings().validar_configuracion()


@pytest.mark.parametrize(
    ("sensor_tokens", "mensaje"),
    [
        ("no-es-json", "JSON válido"),
        ('["S-PES-01"]', "objeto JSON"),
        (json.dumps({**TOKENS_VALIDOS, "S-VER-01": ""}), "S-VER-01"),
        (json.dumps({k: v for k, v in TOKENS_VALIDOS.items() if k != "S-CON-01"}), "S-CON-01"),
    ],
    ids=["json-invalido", "no-es-objeto", "token-vacio", "sensor-faltante"],
)
def test_produccion_con_sensor_tokens_invalidos_lanza(monkeypatch, sensor_tokens, mensaje):
    _configurar_produccion(monkeypatch, SENSOR_TOKENS=sensor_tokens)

    with pytest.raises(RuntimeError, match=mensaje):
        get_settings().validar_configuracion()


def test_produccion_completa_no_lanza(monkeypatch):
    _configurar_produccion(monkeypatch)

    get_settings().validar_configuracion()  # no debe lanzar


def test_render_sin_entorno_con_secreto_por_defecto_lanza(monkeypatch):
    """Render define RENDER=true; un ENTORNO olvidado no debe dejar la API en demo."""
    _configurar_produccion(monkeypatch, entorno=None, JWT_SECRET=JWT_SECRET_POR_DEFECTO)
    monkeypatch.setenv("RENDER", "true")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings().validar_configuracion()


def test_render_sin_entorno_con_configuracion_completa_no_lanza(monkeypatch):
    _configurar_produccion(monkeypatch, entorno=None)
    monkeypatch.setenv("RENDER", "true")

    get_settings().validar_configuracion()  # no debe lanzar


def test_create_app_en_produccion_con_secreto_por_defecto_lanza(monkeypatch):
    _configurar_produccion(monkeypatch, JWT_SECRET=JWT_SECRET_POR_DEFECTO)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_app()


def test_escala_tiempo_cero_falla_al_iniciar(monkeypatch):
    """ESCALA_TIEMPO=0 dividiría entre cero; debe romper al construir Settings."""
    monkeypatch.setenv("ESCALA_TIEMPO", "0")

    with pytest.raises(ValidationError):
        get_settings()


# --- Parser compartido de SENSOR_TOKENS -------------------------------------


def test_leer_sensor_tokens_parsea_un_valor_explicito():
    assert leer_sensor_tokens(json.dumps(TOKENS_VALIDOS)) == TOKENS_VALIDOS


def test_leer_sensor_tokens_usa_la_configuracion_por_defecto(monkeypatch):
    monkeypatch.setenv("SENSOR_TOKENS", json.dumps(TOKENS_VALIDOS))

    assert leer_sensor_tokens() == TOKENS_VALIDOS


@pytest.mark.parametrize(
    ("valor", "mensaje"),
    [
        ("no-es-json", "JSON válido"),
        ('["S-PES-01"]', "objeto JSON"),
        ('{"S-PES-01": 1}', "tokens de texto"),
    ],
    ids=["json-invalido", "no-es-objeto", "token-no-texto"],
)
def test_leer_sensor_tokens_invalido_lanza_valueerror(valor, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        leer_sensor_tokens(valor)
