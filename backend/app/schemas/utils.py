"""Utilidades de serialización compartidas por los endpoints y los eventos SSE."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError


def iso(valor: datetime | date | None) -> str | None:
    """Serializa fechas para JSON; si llegan sin zona, asume UTC."""
    if valor is None:
        return None
    if isinstance(valor, datetime) and valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.isoformat()


def flotante(valor: Decimal | float | int | None) -> float | None:
    """Convierte un numeric de Postgres a float para que el JSON sea numérico."""
    return None if valor is None else float(valor)


def errores_de_validacion(error: ValidationError) -> list[dict[str, Any]]:
    """Errores de Pydantic con la misma forma que los de FastAPI.

    Un PATCH valida la configuración mezclada en el endpoint, no en el parser
    del body; sin esto los `loc` saldrían sin el prefijo `body` y el dashboard
    no podría mapearlos igual que los de un POST.
    """
    return [
        {**detalle, "loc": ("body", *detalle["loc"])}
        for detalle in error.errors()
    ]
