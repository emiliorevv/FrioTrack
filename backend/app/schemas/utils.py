"""Utilidades de serialización compartidas por los endpoints y los eventos SSE."""

from datetime import UTC, date, datetime


def iso(valor: datetime | date | None) -> str | None:
    """Serializa fechas para JSON; si llegan sin zona, asume UTC."""
    if valor is None:
        return None
    if isinstance(valor, datetime) and valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.isoformat()
