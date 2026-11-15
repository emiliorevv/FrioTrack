"""Autenticación: cabecera `Authorization`, JWT de usuario y dependencias de rol."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Usuario
from app.db.session import get_db

PREFIJO_BEARER = "Bearer "
ALGORITMO_JWT = "HS256"

MENSAJE_TOKEN_AUSENTE = (
    "Token de usuario ausente o mal formado: usa `Authorization: Bearer <jwt>`."
)
MENSAJE_TOKEN_STREAM_AUSENTE = (
    "Token de usuario ausente: agrega `?token=<jwt>` a la conexión del stream."
)
MENSAJE_TOKEN_INVALIDO = "Token de usuario inválido o expirado."

SesionDb = Annotated[Session, Depends(get_db)]
Autorizacion = Annotated[str | None, Header(alias="Authorization")]


def token_bearer(authorization: str | None) -> str:
    """Devuelve el token de `Authorization: Bearer <token>` o "" si falta/mal formado."""
    if not authorization or not authorization.startswith(PREFIJO_BEARER):
        return ""
    return authorization.removeprefix(PREFIJO_BEARER).strip()


def crear_token(usuario: str, rol: str) -> str:
    """Firma un JWT HS256 con `sub`, `rol`, `iat` y `exp` (JWT_EXPIRA_HORAS)."""
    ahora = datetime.now(UTC)
    payload = {
        "sub": usuario,
        "rol": rol,
        "iat": ahora,
        "exp": ahora + timedelta(hours=get_settings().jwt_expira_horas),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGORITMO_JWT)


def decodificar_token(token: str) -> dict[str, Any]:
    """Valida la firma y la expiración; lanza `jwt.InvalidTokenError` si falla."""
    return jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=[ALGORITMO_JWT],
        options={"require": ["sub", "rol", "exp"]},
    )


def _no_autorizado(detalle: str) -> HTTPException:
    """401 con `WWW-Authenticate: Bearer`, como pide el contrato."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _usuario_del_token(request: Request, db: Session, token: str) -> Usuario:
    """Decodifica el JWT, carga el usuario y lo deja anotado para los logs."""
    try:
        payload = decodificar_token(token)
    except jwt.InvalidTokenError as error:
        raise _no_autorizado(MENSAJE_TOKEN_INVALIDO) from error

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise _no_autorizado(MENSAJE_TOKEN_INVALIDO)

    usuario = db.scalar(select(Usuario).where(Usuario.usuario == sub))
    if usuario is None:
        # Mismo mensaje que un token inválido: no se filtra si el usuario existe.
        raise _no_autorizado(MENSAJE_TOKEN_INVALIDO)

    # El middleware de acceso toma estos valores para `logs_acceso`.
    request.state.credencial = "usuario"
    request.state.sujeto = usuario.usuario
    return usuario


def get_current_user(
    request: Request,
    db: SesionDb,
    authorization: Autorizacion = None,
) -> Usuario | None:
    """Usuario del JWT de `Authorization: Bearer <jwt>`.

    Con `AUTH_REQUERIDA=0` devuelve None y las rutas de consulta quedan abiertas
    (desarrollo y pruebas). Con `AUTH_REQUERIDA=1` exige un token válido.
    """
    if not get_settings().auth_requerida:
        return None

    token = token_bearer(authorization)
    if not token:
        raise _no_autorizado(MENSAJE_TOKEN_AUSENTE)
    return _usuario_del_token(request, db, token)


def get_current_user_stream(
    request: Request,
    db: SesionDb,
    token: Annotated[str | None, Query()] = None,
) -> Usuario | None:
    """Usuario del JWT que viaja en `?token=` (EventSource no manda headers)."""
    if not get_settings().auth_requerida:
        return None
    if not token:
        raise _no_autorizado(MENSAJE_TOKEN_STREAM_AUSENTE)
    return _usuario_del_token(request, db, token)


def require_rol(*roles: str) -> Callable[..., Usuario | None]:
    """Dependencia que exige uno de `roles`; con auth apagada deja pasar (None)."""

    def dependencia(
        usuario: Annotated[Usuario | None, Depends(get_current_user)],
    ) -> Usuario | None:
        if usuario is None:
            return None
        if usuario.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes: se requiere rol {' o '.join(roles)}.",
            )
        return usuario

    return dependencia
