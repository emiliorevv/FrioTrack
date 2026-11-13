"""Pruebas del simulador de sensores; sin red real ni esperas."""

import json
from datetime import datetime
from typing import Any

import pytest

from simulator.cli import (
    SENSORES_POR_CAMARA,
    ErrorConfiguracion,
    buscar_camara,
    main,
    token_de_camara,
)
from simulator.cliente import Respuesta
from simulator.escenarios import (
    falla_compresor,
    normal,
    puerta_abierta,
    recuperar,
    siguiente_lectura,
)

TOKENS = {
    "S-PES-01": "token-pes",
    "S-CAR-01": "token-car",
    "S-LAC-01": "token-lac",
    "S-VER-01": "token-ver",
    "S-CON-01": "token-con",
}


@pytest.fixture(autouse=True)
def _prohibido_crear_clientes_http(monkeypatch):
    """Si una prueba intenta crear un cliente httpx real, falla de inmediato."""

    def cliente_prohibido(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Las pruebas del simulador no deben abrir conexiones HTTP.")

    monkeypatch.setattr("simulator.cliente.httpx.Client", cliente_prohibido)


class ClienteFalso:
    """Cliente de prueba: captura lo enviado y responde sin tocar la red."""

    def __init__(
        self,
        camaras: list[dict[str, Any]],
        respuesta: Respuesta | None = None,
    ) -> None:
        self.camaras = camaras
        self.respuesta = respuesta or Respuesta(
            202, {"lectura_id": 1, "estado_camara": "en_rango"}
        )
        self.enviadas: list[tuple[dict[str, Any], str]] = []
        self.cerrado = False

    def listar_camaras(self) -> list[dict[str, Any]]:
        return self.camaras

    def enviar_lectura(self, datos: dict[str, Any], token: str) -> Respuesta:
        self.enviadas.append((datos, token))
        return self.respuesta

    def cerrar(self) -> None:
        self.cerrado = True


def _camara_payload(
    camara_id: int = 1,
    rango_min_c: float = 0.0,
    rango_max_c: float = 2.0,
    temperatura_c: float | None = 1.4,
    humedad_pct: float | None = 85.5,
) -> dict[str, Any]:
    return {
        "id": camara_id,
        "nombre": "Pescados y mariscos",
        "rango_min_c": rango_min_c,
        "rango_max_c": rango_max_c,
        "min_para_riesgo": 10,
        "min_para_merma": 60,
        "estado": "en_rango",
        "ultima_lectura": {
            "ts": "2026-11-18T19:05:00-06:00",
            "temperatura_c": temperatura_c,
            "humedad_pct": humedad_pct,
            "puerta_abierta": False,
        },
        "valor_en_riesgo_mxn": 0.0,
    }


def _no_dormir(_segundos: float) -> None:
    raise AssertionError("No debería dormir en esta prueba.")


# --- Escenarios -------------------------------------------------------------


@pytest.mark.parametrize(
    ("azar", "esperada"),
    [(-1.0, 0.7), (0.0, 1.0), (1.0, 1.3)],
    ids=["ruido-minimo", "sin-ruido", "ruido-maximo"],
)
def test_normal_usa_el_centro_del_rango_con_ruido(azar, esperada):
    lectura = normal(0.0, 2.0, 3.0, azar)

    assert lectura.temperatura_c == pytest.approx(esperada)
    assert lectura.puerta_abierta is False


def test_normal_del_congelador_usa_su_propio_centro():
    lectura = normal(-22.0, -18.0, None, 0.0)

    assert lectura.temperatura_c == pytest.approx(-20.0)


def test_puerta_abierta_sube_dos_decimas_y_abre_la_puerta():
    lectura = puerta_abierta(0.0, 2.0, 1.0, 0.9)

    assert lectura.temperatura_c == pytest.approx(1.2)
    assert lectura.puerta_abierta is True


def test_puerta_abierta_sin_lectura_anterior_parte_del_centro():
    lectura = puerta_abierta(0.0, 2.0, None, 0.0)

    assert lectura.temperatura_c == pytest.approx(1.2)
    assert lectura.puerta_abierta is True


def test_falla_compresor_sube_cuatro_decimas_con_puerta_cerrada():
    lectura = falla_compresor(0.0, 2.0, 1.0, 0.9)

    assert lectura.temperatura_c == pytest.approx(1.4)
    assert lectura.puerta_abierta is False


def test_falla_compresor_acumula_la_subida():
    temperatura = 1.0
    for _ in range(3):
        temperatura = falla_compresor(0.0, 2.0, temperatura, 0.0).temperatura_c

    assert temperatura == pytest.approx(2.2)


def test_recuperar_baja_medio_grado_por_lectura_hasta_el_centro():
    temperatura = 3.1
    temperaturas = []
    for _ in range(5):
        lectura = recuperar(0.0, 2.0, temperatura, 0.0)
        temperatura = lectura.temperatura_c
        temperaturas.append(temperatura)
        assert lectura.puerta_abierta is False

    # 2.6 y 2.1 siguen fuera del rango; 1.6 entra y después sigue el normal.
    assert temperaturas == pytest.approx([2.6, 2.1, 1.6, 1.0, 1.0])


def test_recuperar_desde_abajo_del_rango_tambien_llega_al_centro():
    temperatura = -1.0
    temperaturas = []
    for _ in range(4):
        temperatura = recuperar(0.0, 2.0, temperatura, 0.0).temperatura_c
        temperaturas.append(temperatura)

    assert temperaturas == pytest.approx([-0.5, 0.0, 1.0, 1.0])


def test_recuperar_dentro_del_rango_se_comporta_como_normal():
    lectura = recuperar(0.0, 2.0, 2.0, 1.0)

    assert lectura.temperatura_c == pytest.approx(1.3)
    assert lectura.puerta_abierta is False


def test_siguiente_lectura_despacha_el_escenario_y_rechaza_desconocidos():
    assert siguiente_lectura("normal", 0.0, 2.0, 9.0, 0.0).temperatura_c == 1.0

    with pytest.raises(ValueError, match="desconocido"):
        siguiente_lectura("otro", 0.0, 2.0, None, 0.0)


# --- Tokens y cámara --------------------------------------------------------


def test_mapeo_de_sensores_es_el_del_contrato():
    assert SENSORES_POR_CAMARA == {
        1: "S-PES-01",
        2: "S-CAR-01",
        3: "S-LAC-01",
        4: "S-VER-01",
        5: "S-CON-01",
    }


@pytest.mark.parametrize(("camara_id", "sensor_id"), sorted(SENSORES_POR_CAMARA.items()))
def test_token_de_camara_sale_del_sensor_correspondiente(camara_id, sensor_id):
    entorno = {"SENSOR_TOKENS": json.dumps(TOKENS)}

    assert token_de_camara(camara_id, entorno=entorno) == TOKENS[sensor_id]


def test_token_manual_sobreescribe_el_entorno():
    assert token_de_camara(1, "  token-manual  ", entorno={}) == "token-manual"


def test_token_de_camara_sin_sensor_falla():
    with pytest.raises(ErrorConfiguracion, match="cámara 99"):
        token_de_camara(99, entorno={"SENSOR_TOKENS": json.dumps(TOKENS)})


def test_token_de_sensor_ausente_falla():
    with pytest.raises(ErrorConfiguracion, match="S-PES-01"):
        token_de_camara(1, entorno={"SENSOR_TOKENS": json.dumps({"S-CAR-01": "x"})})


@pytest.mark.parametrize("crudo", ["no-es-json", "[]", '"texto"'])
def test_sensor_tokens_invalido_falla(crudo):
    with pytest.raises(ErrorConfiguracion, match="SENSOR_TOKENS"):
        token_de_camara(1, entorno={"SENSOR_TOKENS": crudo})


def test_buscar_camara_toma_rango_y_ultima_lectura():
    camara = buscar_camara([_camara_payload()], 1)

    assert camara.rango_min_c == 0.0
    assert camara.rango_max_c == 2.0
    assert camara.ultima_temperatura_c == 1.4
    assert camara.ultima_humedad_pct == 85.5


def test_buscar_camara_sin_ultima_lectura_deja_los_valores_en_none():
    payload = _camara_payload()
    payload["ultima_lectura"] = None

    camara = buscar_camara([payload], 1)

    assert camara.ultima_temperatura_c is None
    assert camara.ultima_humedad_pct is None


# --- CLI --------------------------------------------------------------------


def test_cli_envia_una_lectura_con_token_y_payload_del_contrato(capsys):
    fake = ClienteFalso([_camara_payload()])

    codigo = main(
        ["--escenario", "normal", "--camara", "1", "--iteraciones", "1", "--token", "tok"],
        cliente=fake,
        dormir=_no_dormir,
        azar=lambda: 0.0,
    )

    assert codigo == 0
    assert fake.cerrado is True
    assert len(fake.enviadas) == 1

    datos, token = fake.enviadas[0]
    assert token == "tok"
    assert set(datos) == {
        "sensor_id",
        "camara_id",
        "ts",
        "temperatura_c",
        "humedad_pct",
        "puerta_abierta",
    }
    assert datos["sensor_id"] == "S-PES-01"
    assert datos["camara_id"] == 1
    assert datos["temperatura_c"] == pytest.approx(1.0)
    assert datos["humedad_pct"] == pytest.approx(85.5)
    assert datos["puerta_abierta"] is False

    ts = datetime.fromisoformat(datos["ts"])
    assert ts.tzinfo is not None
    assert ts.utcoffset() is not None

    salida = capsys.readouterr().out
    assert "cámara 1" in salida
    assert "1.00 °C" in salida
    assert "en_rango" in salida


def test_cli_lee_el_token_de_sensor_tokens(monkeypatch):
    monkeypatch.setenv("SENSOR_TOKENS", json.dumps(TOKENS))
    fake = ClienteFalso([_camara_payload()])

    codigo = main(
        ["--camara", "1", "--iteraciones", "1"],
        cliente=fake,
        dormir=_no_dormir,
        azar=lambda: 0.0,
    )

    assert codigo == 0
    assert fake.enviadas[0][1] == "token-pes"


def test_cli_respeta_iteraciones_y_duerme_entre_lecturas():
    esperas: list[float] = []
    fake = ClienteFalso([_camara_payload()])

    codigo = main(
        ["--iteraciones", "2", "--intervalo", "0.5", "--token", "tok"],
        cliente=fake,
        dormir=esperas.append,
        azar=lambda: 0.0,
    )

    assert codigo == 0
    assert len(fake.enviadas) == 2
    assert esperas == [0.5]


def test_cli_falla_claro_si_la_camara_no_existe(capsys):
    fake = ClienteFalso([_camara_payload(camara_id=1)])

    codigo = main(
        ["--camara", "7", "--iteraciones", "1", "--token", "tok"],
        cliente=fake,
        dormir=_no_dormir,
    )

    assert codigo == 1
    assert fake.enviadas == []
    error = capsys.readouterr().err
    assert "cámara 7" in error
    assert "no existe" in error


def test_cli_falla_si_no_hay_token(capsys, monkeypatch):
    monkeypatch.delenv("SENSOR_TOKENS", raising=False)
    fake = ClienteFalso([_camara_payload()])

    codigo = main(
        ["--camara", "1", "--iteraciones", "1"],
        cliente=fake,
        dormir=_no_dormir,
        azar=lambda: 0.0,
    )

    assert codigo == 1
    assert fake.enviadas == []
    assert "S-PES-01" in capsys.readouterr().err


@pytest.mark.parametrize("status_code", [401, 403])
def test_cli_termina_si_el_api_rechaza_la_credencial(status_code, capsys):
    fake = ClienteFalso(
        [_camara_payload()],
        Respuesta(status_code, {"detail": "Token inválido"}),
    )

    codigo = main(
        ["--iteraciones", "1", "--token", "malo"],
        cliente=fake,
        dormir=_no_dormir,
        azar=lambda: 0.0,
    )

    assert codigo == 1
    assert len(fake.enviadas) == 1
    assert "Token inválido" in capsys.readouterr().err


def test_cli_usa_humedad_de_demo_y_centro_si_no_hay_ultima_lectura():
    payload = _camara_payload()
    payload["ultima_lectura"] = None
    fake = ClienteFalso([payload])

    codigo = main(
        ["--iteraciones", "1", "--token", "tok"],
        cliente=fake,
        dormir=_no_dormir,
        azar=lambda: 0.0,
    )

    assert codigo == 0
    datos = fake.enviadas[0][0]
    assert datos["humedad_pct"] == pytest.approx(80.0)
    assert datos["temperatura_c"] == pytest.approx(1.0)


def test_cli_falla_compresor_parte_de_la_ultima_lectura():
    fake = ClienteFalso([_camara_payload(temperatura_c=3.1)])

    codigo = main(
        ["--escenario", "falla_compresor", "--iteraciones", "1", "--token", "tok"],
        cliente=fake,
        dormir=_no_dormir,
        azar=lambda: 0.0,
    )

    assert codigo == 0
    assert fake.enviadas[0][0]["temperatura_c"] == pytest.approx(3.5)
