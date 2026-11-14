"""Pruebas del script de ataque: arma la petición sin tocar la red."""

from __future__ import annotations

import json
from datetime import datetime

from security.ataque import construir_peticion


def test_construir_peticion_usa_un_token_falso_por_indice():
    peticion = construir_peticion(3)

    assert peticion.metodo == "POST"
    assert peticion.ruta == "/telemetria"
    assert peticion.headers["Authorization"] == "Bearer token-falso-3"
    assert peticion.headers["Content-Type"] == "application/json"


def test_payload_es_una_lectura_valida():
    peticion = construir_peticion(1)

    cuerpo = json.loads(peticion.cuerpo)

    assert cuerpo["sensor_id"] == "S-PES-01"
    assert cuerpo["camara_id"] == 1
    assert cuerpo["temperatura_c"] == 1.4
    assert cuerpo["humedad_pct"] == 88
    assert cuerpo["puerta_abierta"] is False


def test_el_ts_lleva_zona_horaria():
    cuerpo = json.loads(construir_peticion(1).cuerpo)

    ts = datetime.fromisoformat(cuerpo["ts"])

    assert ts.tzinfo is not None
    assert ts.utcoffset() is not None
