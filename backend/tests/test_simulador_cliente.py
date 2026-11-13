"""Pruebas de `ClienteHTTP` con `httpx.MockTransport`; sin red."""

import json

import httpx
import pytest

from simulator.cliente import ClienteHTTP, ErrorAPI, Respuesta


def _cliente(transporte: httpx.BaseTransport) -> ClienteHTTP:
    return ClienteHTTP("http://api.test/api", transporte=transporte)


def test_listar_camaras_une_la_url_sin_doble_diagonal():
    vistas: list[httpx.Request] = []

    def handler(peticion: httpx.Request) -> httpx.Response:
        vistas.append(peticion)
        return httpx.Response(200, json=[{"id": 1, "rango_min_c": 0.0}])

    cliente = ClienteHTTP("http://api.test/api/", transporte=httpx.MockTransport(handler))
    try:
        assert cliente.listar_camaras() == [{"id": 1, "rango_min_c": 0.0}]
    finally:
        cliente.cerrar()

    assert str(vistas[0].url) == "http://api.test/api/camaras"


def test_enviar_lectura_manda_el_bearer_y_devuelve_la_respuesta():
    datos = {
        "sensor_id": "S-PES-01",
        "camara_id": 1,
        "ts": "2026-11-18T19:05:00-06:00",
        "temperatura_c": 1.0,
        "humedad_pct": 85.5,
        "puerta_abierta": False,
    }
    recibidas: list[httpx.Request] = []

    def handler(peticion: httpx.Request) -> httpx.Response:
        recibidas.append(peticion)
        return httpx.Response(202, json={"lectura_id": 7, "estado_camara": "alerta"})

    cliente = _cliente(httpx.MockTransport(handler))
    try:
        respuesta = cliente.enviar_lectura(datos, "token-sensor")
    finally:
        cliente.cerrar()

    assert respuesta == Respuesta(202, {"lectura_id": 7, "estado_camara": "alerta"})
    assert len(recibidas) == 1
    peticion = recibidas[0]
    assert peticion.method == "POST"
    assert str(peticion.url) == "http://api.test/api/telemetria"
    assert peticion.headers["Authorization"] == "Bearer token-sensor"
    assert json.loads(peticion.content) == datos


@pytest.mark.parametrize(
    "cuerpo",
    [b"texto plano", b"[1, 2]"],
    ids=["no-json", "json-que-no-es-objeto"],
)
def test_enviar_lectura_con_cuerpo_no_objeto_devuelve_datos_vacios(cuerpo):
    cliente = _cliente(
        httpx.MockTransport(lambda _peticion: httpx.Response(202, content=cuerpo))
    )
    try:
        respuesta = cliente.enviar_lectura({"sensor_id": "S-PES-01"}, "token")
    finally:
        cliente.cerrar()

    assert respuesta == Respuesta(202, {})


def test_listar_camaras_falla_si_la_respuesta_no_es_json():
    cliente = _cliente(
        httpx.MockTransport(lambda _peticion: httpx.Response(200, content=b"<html>"))
    )
    try:
        with pytest.raises(ErrorAPI, match="JSON válido"):
            cliente.listar_camaras()
    finally:
        cliente.cerrar()


def test_listar_camaras_falla_si_el_json_no_es_una_lista():
    cliente = _cliente(
        httpx.MockTransport(lambda _peticion: httpx.Response(200, json={"id": 1}))
    )
    try:
        with pytest.raises(ErrorAPI, match="lista de cámaras"):
            cliente.listar_camaras()
    finally:
        cliente.cerrar()


def test_listar_camaras_falla_con_status_distinto_de_200():
    cliente = _cliente(
        httpx.MockTransport(lambda _peticion: httpx.Response(503, text="sin servicio"))
    )
    try:
        with pytest.raises(ErrorAPI, match="503"):
            cliente.listar_camaras()
    finally:
        cliente.cerrar()


@pytest.mark.parametrize(
    ("metodo", "mensaje"),
    [
        (lambda cliente: cliente.listar_camaras(), "No se pudo conectar"),
        (lambda cliente: cliente.enviar_lectura({}, "token"), "No se pudo enviar"),
    ],
    ids=["listar", "enviar"],
)
@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError, httpx.ReadTimeout],
    ids=["conexion", "timeout"],
)
def test_los_errores_de_transporte_se_convierten_en_errorapi(metodo, mensaje, error):
    def handler(peticion: httpx.Request) -> httpx.Response:
        raise error("sin red", request=peticion)

    cliente = _cliente(httpx.MockTransport(handler))
    try:
        with pytest.raises(ErrorAPI, match=mensaje):
            metodo(cliente)
    finally:
        cliente.cerrar()
