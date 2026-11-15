"""Esquemas de `POST /api/auth/login`."""

from pydantic import BaseModel, Field


class LoginEntrada(BaseModel):
    """Credenciales del dashboard, con topes para no aceptar cuerpos enormes."""

    usuario: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenSalida(BaseModel):
    """JWT de usuario y datos para que el dashboard programe su renovación."""

    access_token: str
    token_type: str = "bearer"
    expira_en_segundos: int
