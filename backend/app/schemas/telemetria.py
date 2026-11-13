"""Esquemas de `POST /api/telemetria` (ver docs/contrato-api.md)."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TelemetriaIn(BaseModel):
    """Lectura que manda un sensor o el simulador."""

    sensor_id: str
    camara_id: int
    ts: datetime
    # Límites físicos: fuera de ellos la lectura es imposible, no solo sospechosa.
    temperatura_c: float = Field(ge=-40, le=60)
    humedad_pct: float = Field(ge=0, le=100)
    puerta_abierta: bool

    @field_validator("ts")
    @classmethod
    def validar_ts_con_zona(cls, valor: datetime) -> datetime:
        """El contrato exige ISO 8601 con zona horaria; un `ts` naive no es válido."""
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError("ts debe incluir zona horaria (por ejemplo -06:00 o Z)")
        return valor


class TelemetriaOut(BaseModel):
    """Acuse de la lectura ya procesada."""

    lectura_id: int
    estado_camara: str
