"""Esquemas de `POST /api/auth/login` y `POST /api/auth/registro`."""

from pydantic import BaseModel, Field, field_validator


def _normalizar_usuario(valor: object) -> object:
    """Recorta y pasa a minúsculas: `Dueno@Norte.mx` y `dueno@norte.mx` son el mismo login."""
    return valor.strip().lower() if isinstance(valor, str) else valor


class LoginEntrada(BaseModel):
    """Credenciales del dashboard, con topes para no aceptar cuerpos enormes."""

    usuario: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("usuario", mode="before")
    @classmethod
    def _usuario_normalizado(cls, valor: object) -> object:
        return _normalizar_usuario(valor)


class RegistroEntrada(BaseModel):
    """Alta de un restaurante y su usuario dueño.

    `usuario` es el identificador de login (el dashboard puede pedirlo como
    correo): el esquema todavía no tiene `email` ni verificación de correo, así
    que no se agrega un campo que aún no se valida ni se usa.
    """

    restaurante: str = Field(min_length=2, max_length=120)
    usuario: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("restaurante", mode="before")
    @classmethod
    def _recortar_restaurante(cls, valor: object) -> object:
        """Solo recorta: el nombre del restaurante conserva sus mayúsculas."""
        return valor.strip() if isinstance(valor, str) else valor

    @field_validator("usuario", mode="before")
    @classmethod
    def _usuario_normalizado(cls, valor: object) -> object:
        return _normalizar_usuario(valor)


class TokenSalida(BaseModel):
    """JWT de usuario y datos para que el dashboard programe su renovación."""

    access_token: str
    token_type: str = "bearer"
    expira_en_segundos: int
