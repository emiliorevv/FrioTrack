"""Esquemas de `POST /api/auth/login`."""

from pydantic import BaseModel


class LoginEntrada(BaseModel):
    """Credenciales del dashboard."""

    usuario: str
    password: str


class TokenSalida(BaseModel):
    """JWT de usuario y datos para que el dashboard programe su renovación."""

    access_token: str
    token_type: str = "bearer"
    expira_en_segundos: int
