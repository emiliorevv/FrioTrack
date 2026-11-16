"""Esquemas de alta y edición de lotes de inventario (ver docs/contrato-api.md)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Una sola fuente de límites para el alta y la edición. Los decimales siguen la
# precisión de la BD (`numeric(8,2)` y `numeric(10,2)`): no se redondea nada.
NombreProducto = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=120),
]
CantidadLote = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)]
CostoLote = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
UnidadLote = Literal["kg", "l", "pz"]


class LoteCreacion(BaseModel):
    """Body de `POST /lotes` y validación final del PATCH mezclado."""

    model_config = ConfigDict(extra="forbid")

    producto: NombreProducto
    camara_id: int = Field(gt=0)
    cantidad: CantidadLote
    unidad: UnidadLote
    costo_total_mxn: CostoLote
    caducidad: date


class LoteActualizacion(BaseModel):
    """Body de `PATCH /lotes/{id}`: solo inventario, nunca estado ni merma."""

    model_config = ConfigDict(extra="forbid")

    producto: NombreProducto | None = None
    camara_id: int | None = Field(default=None, gt=0)
    cantidad: CantidadLote | None = None
    unidad: UnidadLote | None = None
    costo_total_mxn: CostoLote | None = None
    caducidad: date | None = None
