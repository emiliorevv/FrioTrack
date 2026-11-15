"""Esquemas del CRUD de sensores (ver docs/contrato-api.md)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SensorCreacion(BaseModel):
    """Body opcional de `POST /camaras/{id}/sensores`; el id se autogenera si falta."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str | None = Field(default=None, min_length=1, max_length=64)


class SensorActualizacion(BaseModel):
    """Body de `PATCH /sensores/{id}`: solo el interruptor de activo."""

    model_config = ConfigDict(extra="forbid")

    activo: bool


class SensorSalida(BaseModel):
    """Sensor sin secretos; es lo que se lista y se devuelve en las altas."""

    id: str
    camara_id: int
    activo: bool


class SensorConTokenSalida(BaseModel):
    """Respuesta de alta/rotación: el token en claro se ve una sola vez."""

    sensor: SensorSalida
    token: str


class SensorListaSalida(SensorSalida):
    """Sensor con el nombre de su cámara y la última lectura recibida."""

    camara_nombre: str
    ultima_lectura: str | None
