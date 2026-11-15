"""Esquemas de alta y edición de cámaras (ver docs/contrato-api.md)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Tipos compartidos por el alta y la edición: una sola fuente de límites.
# Los rangos usan Decimal con un decimal porque la BD es `numeric(4,1)`;
# aceptar floats con más precisión dejaría que Postgres redondee en silencio.
NombreCamara = Annotated[str, Field(min_length=2, max_length=120)]
RangoCamara = Annotated[
    Decimal,
    Field(ge=-50, le=50, max_digits=4, decimal_places=1),
]
MinutosCamara = Annotated[int, Field(ge=1)]


class CamaraCreacion(BaseModel):
    """Body de `POST /camaras` y validación final de `PATCH /camaras/{id}`."""

    model_config = ConfigDict(extra="forbid")

    nombre: NombreCamara
    rango_min_c: RangoCamara
    rango_max_c: RangoCamara
    min_para_riesgo: MinutosCamara
    min_para_merma: MinutosCamara

    @field_validator("nombre", mode="before")
    @classmethod
    def _recortar_nombre(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def _rangos_coherentes(self) -> CamaraCreacion:
        """La merma es la etapa siguiente al riesgo y el rango no se invierte."""
        if self.rango_min_c >= self.rango_max_c:
            raise ValueError("rango_min_c debe ser menor que rango_max_c")
        if self.min_para_merma <= self.min_para_riesgo:
            raise ValueError("min_para_merma debe ser mayor que min_para_riesgo")
        return self


class CamaraActualizacion(BaseModel):
    """Body de `PATCH /camaras/{id}`: solo configuración, nunca campos de sistema."""

    model_config = ConfigDict(extra="forbid")

    nombre: NombreCamara | None = None
    rango_min_c: RangoCamara | None = None
    rango_max_c: RangoCamara | None = None
    min_para_riesgo: MinutosCamara | None = None
    min_para_merma: MinutosCamara | None = None

    @field_validator("nombre", mode="before")
    @classmethod
    def _recortar_nombre(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor
