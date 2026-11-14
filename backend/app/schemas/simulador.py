"""Esquema de `POST /api/simulador/tick` (ver docs/contrato-api.md)."""

from pydantic import BaseModel


class TickOut(BaseModel):
    """Resultado del tick: lecturas generadas y cámaras saltadas."""

    lecturas: int
    saltadas: list[int]
