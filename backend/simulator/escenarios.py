"""Escenarios del simulador de sensores.

Cada escenario es una función pura: recibe el rango de la cámara, la lectura
anterior y un número de azar en [-1, 1], y regresa la siguiente lectura. Así se
prueban sin esperas ni red.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

RUIDO_NORMAL_C = 0.3
PASO_PUERTA_ABIERTA_C = 0.2
PASO_FALLA_COMPRESOR_C = 0.4
PASO_RECUPERACION_C = 0.5
# Humedad que manda el simulador cuando la API no trae una anterior.
HUMEDAD_POR_DEFECTO = 80.0
# Techo de los escenarios que suben sin control: 10 °C arriba del máximo de la
# cámara, muy por debajo del límite físico de POST /telemetria (60 °C).
TECHO_EXTRA_C = 10.0


@dataclass(frozen=True)
class LecturaSimulada:
    """Temperatura y puerta que mandaría el sensor en una lectura."""

    temperatura_c: float
    puerta_abierta: bool


def _centro(rango_min_c: float, rango_max_c: float) -> float:
    return (rango_min_c + rango_max_c) / 2


def _techo(rango_max_c: float) -> float:
    """Temperatura máxima que alcanza una falla simulada."""
    return rango_max_c + TECHO_EXTRA_C


def _redondear(temperatura: float) -> float:
    """Redondea a 1 decimal, igual que `lecturas.temperatura_c` (Numeric(4, 1))."""
    return round(temperatura, 1)


def normal(
    rango_min_c: float,
    rango_max_c: float,
    _anterior: float | None,
    azar: float,
) -> LecturaSimulada:
    """Centro del rango con ruido de ±0.3 °C y la puerta cerrada."""
    temperatura = _centro(rango_min_c, rango_max_c) + RUIDO_NORMAL_C * azar
    return LecturaSimulada(_redondear(temperatura), False)


def puerta_abierta(
    rango_min_c: float,
    rango_max_c: float,
    anterior: float | None,
    _azar: float,
) -> LecturaSimulada:
    """Puerta abierta y +0.2 °C por lectura, con techo en `rango_max_c + 10`."""
    base = _centro(rango_min_c, rango_max_c) if anterior is None else anterior
    temperatura = min(base + PASO_PUERTA_ABIERTA_C, _techo(rango_max_c))
    return LecturaSimulada(_redondear(temperatura), True)


def falla_compresor(
    rango_min_c: float,
    rango_max_c: float,
    anterior: float | None,
    _azar: float,
) -> LecturaSimulada:
    """Puerta cerrada y +0.4 °C por lectura, con techo en `rango_max_c + 10`."""
    base = _centro(rango_min_c, rango_max_c) if anterior is None else anterior
    temperatura = min(base + PASO_FALLA_COMPRESOR_C, _techo(rango_max_c))
    return LecturaSimulada(_redondear(temperatura), False)


def recuperar(
    rango_min_c: float,
    rango_max_c: float,
    anterior: float | None,
    azar: float,
) -> LecturaSimulada:
    """Acerca la temperatura al centro 0.5 °C por lectura; luego sigue normal.

    Sigue acercándose mientras la distancia al centro sea mayor que
    `PASO_RECUPERACION_C`, aunque ya esté dentro del rango: así la lectura no
    salta de golpe al centro en cuanto cruza el límite.
    """
    if anterior is None:
        return normal(rango_min_c, rango_max_c, anterior, azar)

    centro = _centro(rango_min_c, rango_max_c)
    if abs(anterior - centro) <= PASO_RECUPERACION_C:
        return normal(rango_min_c, rango_max_c, anterior, azar)

    if anterior > centro:
        temperatura = max(centro, anterior - PASO_RECUPERACION_C)
    else:
        temperatura = min(centro, anterior + PASO_RECUPERACION_C)
    return LecturaSimulada(_redondear(temperatura), False)


ESCENARIOS: dict[
    str, Callable[[float, float, float | None, float], LecturaSimulada]
] = {
    "normal": normal,
    "puerta_abierta": puerta_abierta,
    "falla_compresor": falla_compresor,
    "recuperar": recuperar,
}


def siguiente_lectura(
    escenario: str,
    rango_min_c: float,
    rango_max_c: float,
    anterior: float | None,
    azar: float,
) -> LecturaSimulada:
    """Aplica el escenario pedido; `ValueError` si no existe."""
    try:
        funcion = ESCENARIOS[escenario]
    except KeyError:
        raise ValueError(f"Escenario desconocido: {escenario!r}") from None
    return funcion(rango_min_c, rango_max_c, anterior, azar)


def azar_aleatorio() -> float:
    """Número uniforme en [-1, 1] para el ruido del escenario normal."""
    return random.uniform(-1.0, 1.0)
