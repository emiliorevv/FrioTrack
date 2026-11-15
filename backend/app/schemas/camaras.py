"""Esquemas de alta y edición de cámaras (ver docs/contrato-api.md)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def validar_configuracion(
    rango_min_c: float,
    rango_max_c: float,
    min_para_riesgo: int,
    min_para_merma: int,
) -> None:
    """Reglas de configuración compartidas por el alta y la edición.

    `min_para_merma` debe ser **mayor** que `min_para_riesgo`: la merma es la
    etapa siguiente al riesgo y nunca puede ocurrir antes.
    """
    if rango_min_c >= rango_max_c:
        raise ValueError("rango_min_c debe ser menor que rango_max_c")
    if min_para_merma <= min_para_riesgo:
        raise ValueError("min_para_merma debe ser mayor que min_para_riesgo")


class _CamposCamara(BaseModel):
    """Campos de configuración con sus límites, comunes a alta y edición."""

    rango_min_c: float = Field(ge=-50, le=50)
    rango_max_c: float = Field(ge=-50, le=50)
    min_para_riesgo: int = Field(ge=1)
    min_para_merma: int = Field(ge=1)


class CamaraCreacion(_CamposCamara):
    """Body de `POST /camaras`; el tenant y el estado los pone la API."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=2, max_length=120)

    @field_validator("nombre", mode="before")
    @classmethod
    def _recortar_nombre(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def _validar_rangos(self) -> CamaraCreacion:
        validar_configuracion(
            self.rango_min_c,
            self.rango_max_c,
            self.min_para_riesgo,
            self.min_para_merma,
        )
        return self


class CamaraActualizacion(BaseModel):
    """Body de `PATCH /camaras/{id}`: solo configuración, nunca campos de sistema."""

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    rango_min_c: float | None = Field(default=None, ge=-50, le=50)
    rango_max_c: float | None = Field(default=None, ge=-50, le=50)
    min_para_riesgo: int | None = Field(default=None, ge=1)
    min_para_merma: int | None = Field(default=None, ge=1)

    @field_validator("nombre", mode="before")
    @classmethod
    def _recortar_nombre(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def _sin_nulos(self) -> CamaraActualizacion:
        """Un campo enviado como `null` es inválido, no una orden de borrarlo."""
        nulos = [campo for campo in self.model_fields_set if getattr(self, campo) is None]
        if nulos:
            raise ValueError(f"estos campos no pueden ser null: {', '.join(sorted(nulos))}")
        return self


def validar_camara_actualizada(datos: dict[str, Any]) -> None:
    """Aplica las reglas de configuración al resultado de mezclar el PATCH."""
    validar_configuracion(
        float(datos["rango_min_c"]),
        float(datos["rango_max_c"]),
        int(datos["min_para_riesgo"]),
        int(datos["min_para_merma"]),
    )
