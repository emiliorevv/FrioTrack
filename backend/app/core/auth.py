"""Utilidades de autenticación por cabecera `Authorization`."""

PREFIJO_BEARER = "Bearer "


def token_bearer(authorization: str | None) -> str:
    """Devuelve el token de `Authorization: Bearer <token>` o "" si falta/mal formado."""
    if not authorization or not authorization.startswith(PREFIJO_BEARER):
        return ""
    return authorization.removeprefix(PREFIJO_BEARER).strip()
