"""Pruebas de la evaluación pura de lecturas; no tocan base de datos."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.erp.procesador import ResultadoEvaluacion, evaluar_lectura

AHORA = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)
ESCALA = 30  # 10 min de riesgo = 20 s; 60 min de merma = 120 s; puerta = 10 s.


@dataclass
class CamaraFalsa:
    """Cámara mínima para la evaluación, ya con las ventanas actualizadas."""

    rango_min_c: float = 0.0
    rango_max_c: float = 2.0
    min_para_riesgo: int = 10
    min_para_merma: int = 60
    fuera_de_rango_desde: datetime | None = None
    puerta_abierta_desde: datetime | None = None


@dataclass
class LoteFalso:
    """Lote mínimo: la evaluación solo mira su estado."""

    nombre: str
    estado: str = "ok"


@dataclass
class AlertaFalsa:
    """Alerta abierta mínima para la evaluación."""

    tipo: str
    temperatura_max_c: Decimal | None = None


def _evaluar(
    camara: CamaraFalsa,
    *,
    temperatura: float = 1.0,
    puerta_abierta: bool = False,
    ahora: datetime = AHORA,
    lotes: list[LoteFalso] | None = None,
    alertas: list[AlertaFalsa] | None = None,
) -> ResultadoEvaluacion:
    """Atajo para evaluar con la escala de demo de 30."""
    return evaluar_lectura(
        camara,
        temperatura,
        puerta_abierta,
        ahora,
        ESCALA,
        lotes or [],
        alertas or [],
    )


def test_primera_lectura_normal_no_dispara_nada():
    resultado = _evaluar(CamaraFalsa(), lotes=[LoteFalso("Robalo"), LoteFalso("Camarón")])

    assert resultado == ResultadoEvaluacion()


def test_salida_de_rango_antes_del_umbral_no_abre_alerta_ni_marca_lotes():
    camara = CamaraFalsa(fuera_de_rango_desde=AHORA)
    lotes = [LoteFalso("Robalo")]

    resultado = _evaluar(
        camara,
        temperatura=3.0,
        ahora=AHORA + timedelta(seconds=19, milliseconds=999),
        lotes=lotes,
    )

    assert resultado.abrir_alerta_temperatura is False
    assert resultado.lotes_a_riesgo == []
    assert resultado.temperatura_max_c is None


def test_umbral_de_riesgo_abre_alerta_y_marca_todos_los_lotes_ok():
    camara = CamaraFalsa(fuera_de_rango_desde=AHORA)
    lotes = [LoteFalso("Robalo"), LoteFalso("Camarón")]

    resultado = _evaluar(
        camara, temperatura=3.0, ahora=AHORA + timedelta(seconds=20), lotes=lotes
    )

    assert resultado.abrir_alerta_temperatura is True
    assert resultado.lotes_a_riesgo == lotes
    assert resultado.temperatura_max_c == Decimal("3.0")


def test_umbral_de_riesgo_no_repite_lotes_que_ya_estan_en_riesgo():
    camara = CamaraFalsa(fuera_de_rango_desde=AHORA)
    lotes = [LoteFalso("Robalo", "en_riesgo"), LoteFalso("Camarón", "merma")]

    resultado = _evaluar(
        camara, temperatura=3.0, ahora=AHORA + timedelta(seconds=20), lotes=lotes
    )

    assert resultado.lotes_a_riesgo == []
    assert resultado.lotes_a_merma == []


def test_umbral_de_merma_pasa_todos_los_no_merma_y_gana_sobre_riesgo():
    camara = CamaraFalsa(fuera_de_rango_desde=AHORA)
    lotes = [
        LoteFalso("Robalo", "ok"),
        LoteFalso("Camarón", "en_riesgo"),
        LoteFalso("Pulpo", "merma"),
    ]

    resultado = _evaluar(
        camara, temperatura=3.0, ahora=AHORA + timedelta(seconds=120), lotes=lotes
    )

    assert resultado.lotes_a_merma == [lotes[0], lotes[1]]
    assert resultado.lotes_a_riesgo == []
    assert resultado.abrir_alerta_temperatura is True


def test_recuperacion_cierra_alerta_y_regresa_solo_los_lotes_en_riesgo():
    alerta = AlertaFalsa("temperatura", Decimal("3.4"))
    lotes = [
        LoteFalso("Robalo", "en_riesgo"),
        LoteFalso("Camarón", "merma"),
        LoteFalso("Pulpo", "ok"),
    ]

    resultado = _evaluar(CamaraFalsa(), temperatura=1.0, lotes=lotes, alertas=[alerta])

    assert resultado.cerrar_alerta_temperatura is True
    assert resultado.lotes_a_recuperar == [lotes[0]]
    assert lotes[1] not in resultado.lotes_a_recuperar
    assert resultado.abrir_alerta_temperatura is False


@pytest.mark.parametrize(
    ("segundos", "esperado"),
    [(9.999, False), (10.0, True), (10.1, True)],
)
def test_puerta_abre_alerta_a_cinco_minutos_con_escala_30(segundos, esperado):
    camara = CamaraFalsa(puerta_abierta_desde=AHORA)

    resultado = _evaluar(
        camara,
        puerta_abierta=True,
        ahora=AHORA + timedelta(seconds=segundos),
    )

    assert resultado.abrir_alerta_puerta is esperado


def test_puerta_no_duplica_la_alerta_si_ya_esta_abierta():
    camara = CamaraFalsa(puerta_abierta_desde=AHORA)
    alerta = AlertaFalsa("puerta")

    resultado = _evaluar(
        camara,
        puerta_abierta=True,
        ahora=AHORA + timedelta(seconds=60),
        alertas=[alerta],
    )

    assert resultado.abrir_alerta_puerta is False


def test_puerta_cerrada_cierra_la_alerta_abierta():
    alerta = AlertaFalsa("puerta")

    resultado = _evaluar(CamaraFalsa(), puerta_abierta=False, alertas=[alerta])

    assert resultado.cerrar_alerta_puerta is True


def test_temperatura_max_conserva_la_peor_lectura_de_la_alerta():
    alerta = AlertaFalsa("temperatura", Decimal("3.4"))
    camara = CamaraFalsa(fuera_de_rango_desde=AHORA)

    resultado = _evaluar(
        camara,
        temperatura=3.2,
        ahora=AHORA + timedelta(seconds=30),
        alertas=[alerta],
    )

    assert resultado.temperatura_max_c == Decimal("3.4")
    assert resultado.abrir_alerta_temperatura is False


def test_temperatura_max_avanza_cuando_la_lectura_actual_es_peor():
    alerta = AlertaFalsa("temperatura", Decimal("3.4"))
    camara = CamaraFalsa(fuera_de_rango_desde=AHORA)

    resultado = _evaluar(
        camara,
        temperatura=4.1,
        ahora=AHORA + timedelta(seconds=30),
        alertas=[alerta],
    )

    assert resultado.temperatura_max_c == Decimal("4.1")
