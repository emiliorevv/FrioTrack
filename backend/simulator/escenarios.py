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


@dataclass(frozen=True)
class LecturaSimulada:
    """Temperatura y puerta que mandaría el sensor en una lectura."""

    temperatura_c: float
    puerta_abierta: bool


def _centro(rango_min_c: float, rango_max_c: float) -> float:
    return (rango_min_c + rango_max_c) / 2


def normal(
    rango_min_c: float,
    rango_max_c: float,
    _anterior: float | None,
    azar: float,
) -> LecturaSimulada:
    """Centro del rango con ruido de ±0.3 °C y la puerta cerrada."""
    temperatura = _centro(rango_min_c, rango_max_c) + RUIDO_NORMAL_C * azar
    return LecturaSimulada(round(temperatura, 2), False)


def puerta_abierta(
    rango_min_c: float,
    rango_max_c: float,
    anterior: float | None,
    _azar: float,
) -> LecturaSimulada:
    """Puerta abierta y +0.2 °C por lectura."""
    base = _centro(rango_min_c, rango_max_c) if anterior is None else anterior
    return LecturaSimulada(round(base + PASO_PUERTA_ABIERTA_C, 2), True)


def falla_compresor(
    rango_min_c: float,
    rango_max_c: float,
    anterior: float | None,
    _azar: float,
) -> LecturaSimulada:
    """Puerta cerrada y +0.4 °C por lectura."""
    base = _centro(rango_min_c, rango_max_c) if anterior is None else anterior
    return LecturaSimulada(round(base + PASO_FALLA_COMPRESOR_C, 2), False)


def recuperar(
    rango_min_c: float,
    rango_max_c: float,
    anterior: float | None,
    azar: float,
) -> LecturaSimulada:
    """Acerca la temperatura al centro 0.5 °C por lectura y luego sigue normal."""
    if anterior is None or rango_min_c <= anterior <= rango_max_c:
        return normal(rango_min_c, rango_max_c, anterior, azar)

    centro = _centro(rango_min_c, rango_max_c)
    if anterior > centro:
        temperatura = max(centro, anterior - PASO_RECUPERACION_C)
    else:
        temperatura = min(centro, anterior + PASO_RECUPERACION_C)
    return LecturaSimulada(round(temperatura, 2), False)


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
