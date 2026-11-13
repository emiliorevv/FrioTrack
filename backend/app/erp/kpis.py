"""Cálculos de los KPIs de operación como funciones puras, sin base de datos.

Así las pruebas pueden fijar fechas y datos sin levantar Postgres ni mockear
sesiones. El router solo consulta filas y se las pasa a estas funciones.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

ZONA_MEXICO = ZoneInfo("America/Mexico_City")
PeriodoMerma = Literal["dia", "mes"]


def _decimal(valor: Decimal | float | int | str) -> Decimal:
    """Convierte a Decimal sin arrastrar el error de representación de los floats."""
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _con_zona(instante: datetime) -> datetime:
    """Asume UTC cuando la fecha viene sin zona (las de Postgres no)."""
    return instante.replace(tzinfo=UTC) if instante.tzinfo is None else instante


def pct_en_rango(
    lecturas: Iterable[tuple[Decimal | float, Decimal | float, Decimal | float]],
) -> float:
    """Porcentaje de lecturas dentro de su rango, redondeado a 1 decimal.

    Cada fila es `(temperatura, rango_min, rango_max)`; los extremos cuentan
    como dentro de rango. Sin lecturas regresa `0.0`.
    """
    total = 0
    dentro = 0
    for temperatura, minimo, maximo in lecturas:
        total += 1
        if _decimal(minimo) <= _decimal(temperatura) <= _decimal(maximo):
            dentro += 1
    if total == 0:
        return 0.0
    return round(100.0 * dentro / total, 1)


def promedio_respuesta_min(pares: Iterable[tuple[datetime, datetime]]) -> float:
    """Promedio de `(atendida_en - abierta_en)` en minutos, redondeado a 1 decimal.

    Sin pares regresa `0.0`.
    """
    total = 0
    segundos = 0.0
    for abierta_en, atendida_en in pares:
        total += 1
        segundos += (_con_zona(atendida_en) - _con_zona(abierta_en)).total_seconds()
    if total == 0:
        return 0.0
    return round(segundos / total / 60.0, 1)


def merma_en_periodo(
    mermas: Iterable[tuple[datetime, Decimal | float]],
    ahora: datetime,
    periodo: PeriodoMerma,
) -> float:
    """Suma el costo de las mermas del día o mes actual en `America/Mexico_City`.

    Cada fila es `(merma_en, costo_total_mxn)`. `merma_en` se interpreta como UTC
    si llega sin zona y siempre se compara en hora local de Ciudad de México.
    """
    if periodo not in ("dia", "mes"):
        raise ValueError(f"Periodo no soportado: {periodo!r}")

    ahora_local = _con_zona(ahora).astimezone(ZONA_MEXICO)
    total = Decimal("0")
    for merma_en, costo in mermas:
        local = _con_zona(merma_en).astimezone(ZONA_MEXICO)
        if periodo == "dia" and local.date() != ahora_local.date():
            continue
        if periodo == "mes" and (local.year, local.month) != (ahora_local.year, ahora_local.month):
            continue
        total += _decimal(costo)
    return float(round(total, 2))


def valor_en_riesgo(costos: Iterable[Decimal | float]) -> float:
    """Suma el costo de los lotes en riesgo, redondeado a centavos."""
    total = sum((_decimal(costo) for costo in costos), Decimal("0"))
    return float(round(total, 2))
