"""Pruebas de las reglas puras del ERP; no tocan base de datos."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.erp.reglas import (
    asegurar_utc,
    calcular_valor_en_riesgo,
    debe_abrir_alerta_puerta,
    debe_abrir_alerta_temperatura,
    debe_marcar_merma,
    esta_en_rango,
    estado_camara,
    segundos_efectivos,
)

AHORA = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


@dataclass
class LoteFalso:
    """Lote mínimo para probar la suma de valor en riesgo."""

    estado: str
    costo_total_mxn: Decimal


@pytest.mark.parametrize(
    ("temperatura", "esperado"),
    [
        (0.0, True),  # límite inferior exacto
        (2.0, True),  # límite superior exacto
        (1.0, True),
        (-0.1, False),
        (2.1, False),
    ],
)
def test_esta_en_rango_incluye_los_limites(temperatura: float, esperado: bool):
    assert esta_en_rango(temperatura, 0.0, 2.0) is esperado


@pytest.mark.parametrize(
    ("minutos", "escala", "esperado"),
    [(10, 1, 600), (10, 30, 20), (60, 30, 120), (5, 30, 10)],
)
def test_segundos_efectivos_divide_entre_la_escala(
    minutos: float, escala: float, esperado: float
):
    assert segundos_efectivos(minutos, escala) == esperado


@pytest.mark.parametrize("escala", [0, -1, 0.5])
def test_segundos_efectivos_rechaza_escala_invalida(escala: float):
    with pytest.raises(ValueError, match="escala"):
        segundos_efectivos(10, escala)


@pytest.mark.parametrize(
    ("desplazamiento", "esperado"),
    [
        (timedelta(seconds=19, milliseconds=999), False),
        (timedelta(seconds=20), True),
        (timedelta(seconds=20, milliseconds=1), True),
    ],
)
def test_alerta_temperatura_en_el_umbral(desplazamiento: timedelta, esperado: bool):
    # 10 minutos de riesgo con escala 30 = 20 segundos reales.
    assert debe_abrir_alerta_temperatura(AHORA, AHORA + desplazamiento, 10, 30) is esperado


def test_alerta_temperatura_sin_fuera_de_rango_desde():
    assert debe_abrir_alerta_temperatura(None, AHORA, 10, 30) is False


@pytest.mark.parametrize(
    ("desplazamiento", "esperado"),
    [
        (timedelta(seconds=119, milliseconds=999), False),
        (timedelta(seconds=120), True),
        (timedelta(seconds=120, milliseconds=1), True),
    ],
)
def test_merma_en_el_umbral(desplazamiento: timedelta, esperado: bool):
    # 60 minutos de merma con escala 30 = 120 segundos reales.
    assert debe_marcar_merma(AHORA, AHORA + desplazamiento, 60, 30) is esperado


def test_merma_sin_fuera_de_rango_desde():
    assert debe_marcar_merma(None, AHORA, 60, 30) is False


@pytest.mark.parametrize(
    ("desplazamiento", "esperado"),
    [
        (timedelta(seconds=9, milliseconds=999), False),
        (timedelta(seconds=10), True),
        (timedelta(seconds=10, milliseconds=1), True),
    ],
)
def test_alerta_puerta_a_cinco_minutos_con_escala_30(
    desplazamiento: timedelta, esperado: bool
):
    # 5 minutos reales de puerta con escala 30 = 10 segundos.
    assert debe_abrir_alerta_puerta(AHORA, AHORA + desplazamiento, 30) is esperado


@pytest.mark.parametrize(
    ("desplazamiento", "esperado"),
    [
        (timedelta(seconds=299, milliseconds=999), False),
        (timedelta(seconds=300), True),
    ],
)
def test_alerta_puerta_usa_cinco_minutos_por_defecto(
    desplazamiento: timedelta, esperado: bool
):
    assert debe_abrir_alerta_puerta(AHORA, AHORA + desplazamiento, 1) is esperado


def test_alerta_puerta_sin_puerta_abierta_desde():
    assert debe_abrir_alerta_puerta(None, AHORA, 30) is False


@pytest.mark.parametrize(
    ("en_rango", "puerta_abierta", "lotes_en_riesgo", "lotes_en_merma", "esperado"),
    [
        (True, False, 0, 0, "en_rango"),
        (False, False, 0, 0, "alerta"),
        (True, True, 0, 0, "alerta"),
        (True, False, 2, 0, "critica"),
        (True, False, 0, 1, "critica"),
        (False, True, 1, 1, "critica"),
    ],
)
def test_estado_camara(
    en_rango: bool,
    puerta_abierta: bool,
    lotes_en_riesgo: int,
    lotes_en_merma: int,
    esperado: str,
):
    assert (
        estado_camara(
            en_rango=en_rango,
            puerta_abierta=puerta_abierta,
            lotes_en_riesgo=lotes_en_riesgo,
            lotes_en_merma=lotes_en_merma,
        )
        == esperado
    )


def test_valor_en_riesgo_suma_solo_lotes_en_riesgo():
    lotes = [
        LoteFalso("ok", Decimal("100.00")),
        LoteFalso("en_riesgo", Decimal("3240.00")),
        LoteFalso("merma", Decimal("999.99")),
        LoteFalso("en_riesgo", Decimal("1610.50")),
    ]

    assert calcular_valor_en_riesgo(lotes) == Decimal("4850.50")


def test_valor_en_riesgo_sin_lotes_es_cero():
    assert calcular_valor_en_riesgo([]) == Decimal("0")


def test_asegurar_utc_asume_utc_en_datetime_naive():
    naive = datetime(2026, 11, 18, 19, 0)

    assert asegurar_utc(naive) == datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


def test_asegurar_utc_convierte_zonas_a_utc():
    merida = timezone(timedelta(hours=-6))
    local = datetime(2026, 11, 18, 13, 0, tzinfo=merida)

    assert asegurar_utc(local) == datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


def test_reglas_comparan_naive_con_aware():
    desde_naive = datetime(2026, 11, 18, 19, 0)  # se asume UTC
    merida = timezone(timedelta(hours=-6))
    ahora_aware = datetime(2026, 11, 18, 13, 0, 20, tzinfo=merida)  # 19:00:20 UTC

    assert debe_abrir_alerta_temperatura(desde_naive, ahora_aware, 10, 30) is True


def test_reglas_comparan_naive_con_naive_asumiendo_utc():
    desde = datetime(2026, 11, 18, 19, 0)
    ahora = datetime(2026, 11, 18, 19, 0, 20)

    assert debe_abrir_alerta_temperatura(desde, ahora, 10, 30) is True
