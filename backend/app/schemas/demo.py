"""Esquemas de los endpoints de simulación de la demo."""

from pydantic import BaseModel, ConfigDict, Field


class CamaraDemoEntrada(BaseModel):
    """Body opcional de `POST /demo/falla` y `POST /demo/puerta`."""

    model_config = ConfigDict(extra="forbid")

    camara_id: int | None = Field(default=None, gt=0)


class SimulacionOut(BaseModel):
    """Acuse de una simulación lanzada en segundo plano."""

    mensaje: str
    camara_id: int | None = None
