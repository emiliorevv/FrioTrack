"""Reglas puras de frío: rangos, tiempos, alertas y valor en riesgo.

Los tiempos se configuran en minutos reales; ``escala`` los acelera para la demo
(ver ``docs/modo-demo.md``). Los rangos de temperatura no se escalan.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, Protocol

EstadoCamara = Literal["en_rango", "alerta", "critica"]


class LoteValorable(Protocol):
    """Lo mínimo que necesita `calcular_valor_en_riesgo` de un lote."""

    estado: str
    costo_total_mxn: Decimal


def asegurar_utc(valor: datetime) -> datetime:
    """Normaliza a UTC; un datetime sin zona horaria se asume UTC."""
    if valor.tzinfo is None or valor.utcoffset() is None:
        return valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC)


def segundos_efectivos(minutos: float, escala: float) -> float:
    """Convierte minutos configurados a segundos reales según la escala de demo."""
    if escala < 1:
        raise ValueError(f"La escala de tiempo debe ser >= 1, se recibió {escala!r}.")
    return minutos * 60 / escala


def esta_en_rango(temperatura: float, rango_min: float, rango_max: float) -> bool:
    """True si la temperatura está dentro del rango, límites incluidos."""
    return rango_min <= temperatura <= rango_max


def _segundos_transcurridos(desde: datetime, ahora: datetime) -> float:
    """Segundos entre dos fechas, normalizando ambas a UTC para poder restarlas."""
    return (asegurar_utc(ahora) - asegurar_utc(desde)).total_seconds()


def debe_abrir_alerta_temperatura(
    fuera_de_rango_desde: datetime | None,
    ahora: datetime,
    minutos_para_riesgo: float,
    escala: float,
) -> bool:
    """True si ya se cumplió el tiempo fuera de rango para abrir alerta."""
    if fuera_de_rango_desde is None:
        return False
    segundos = _segundos_transcurridos(fuera_de_rango_desde, ahora)
    return segundos >= segundos_efectivos(minutos_para_riesgo, escala)


def debe_marcar_merma(
    fuera_de_rango_desde: datetime | None,
    ahora: datetime,
    minutos_para_merma: float,
    escala: float,
) -> bool:
    """True si ya se cumplió el tiempo fuera de rango para marcar merma."""
    if fuera_de_rango_desde is None:
        return False
    segundos = _segundos_transcurridos(fuera_de_rango_desde, ahora)
    return segundos >= segundos_efectivos(minutos_para_merma, escala)


def debe_abrir_alerta_puerta(
    puerta_abierta_desde: datetime | None,
    ahora: datetime,
    escala: float,
    minutos_para_puerta: float = 5,
) -> bool:
    """True si la puerta lleva abierta el tiempo configurado (5 min reales)."""
    if puerta_abierta_desde is None:
        return False
    segundos = _segundos_transcurridos(puerta_abierta_desde, ahora)
    return segundos >= segundos_efectivos(minutos_para_puerta, escala)


def estado_camara(
    *,
    en_rango: bool,
    puerta_abierta: bool,
    lotes_en_riesgo: int,
    lotes_en_merma: int,
) -> EstadoCamara:
    """Estado de la cámara según `docs/contrato-api.md`."""
    if lotes_en_riesgo > 0 or lotes_en_merma > 0:
        return "critica"
    if not en_rango or puerta_abierta:
        return "alerta"
    return "en_rango"


def calcular_valor_en_riesgo(lotes: Iterable[LoteValorable]) -> Decimal:
    """Suma el costo de los lotes en riesgo; los demás estados no cuentan."""
    return sum(
        (lote.costo_total_mxn for lote in lotes if lote.estado == "en_riesgo"),
        start=Decimal("0"),
    )
