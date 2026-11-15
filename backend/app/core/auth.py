"""Autenticación: cabecera `Authorization`, JWT de usuario y dependencias de rol."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Usuario
from app.db.session import SessionLocal, get_db, get_engine

ALGORITMO_JWT = "HS256"
LONGITUD_HUELLA_PASSWORD = 16

MENSAJE_TOKEN_AUSENTE = (
    "Token de usuario ausente o mal formado: usa `Authorization: Bearer <jwt>`."
)
MENSAJE_TOKEN_STREAM_AUSENTE = (
    "Token de usuario ausente: agrega `?token=<jwt>` a la conexión del stream."
)
MENSAJE_TOKEN_INVALIDO = "Token de usuario inválido o expirado."

SesionDb = Annotated[Session, Depends(get_db)]


def token_bearer(authorization: str | None) -> str:
    """Devuelve el token de `Authorization: <esquema> <token>`.

    El esquema Bearer no distingue mayúsculas (RFC 7235); el token se conserva
    tal cual.
    """
    if not authorization:
        return ""
    partes = authorization.split(maxsplit=1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return ""
    return partes[1].strip()


def huella_password(password_hash: str) -> str:
    """SHA-256 corto del hash guardado; ata el JWT a la contraseña vigente."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:LONGITUD_HUELLA_PASSWORD]


def crear_token(usuario: Usuario) -> str:
    """Firma un JWT HS256 con `sub`, `uid`, `rol`, `pwd`, `iat` y `exp`."""
    ahora = datetime.now(UTC)
    payload = {
        "sub": usuario.usuario,
        "uid": usuario.id,
        "rol": usuario.rol,
        "pwd": huella_password(usuario.password_hash),
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
        options={"require": ["sub", "uid", "rol", "pwd", "exp"]},
    )


def no_autorizado(detalle: str) -> HTTPException:
    """401 con `WWW-Authenticate: Bearer`, como pide el contrato."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def buscar_usuario(db: Session, nombre: str) -> Usuario | None:
    """Busca por nombre de usuario, que es único en la tabla."""
    return db.scalar(select(Usuario).where(Usuario.usuario == nombre))


def sesion_si_auth() -> Iterator[Session | None]:
    """Sesión para autenticar solo si `AUTH_REQUERIDA` está prendida.

    Con la bandera apagada devuelve None sin tocar `get_engine`: el stream y las
    rutas de consulta deben poder funcionar sin `DATABASE_URL`.
    """
    if not get_settings().auth_requerida:
        yield None
        return
    with SessionLocal(bind=get_engine()) as session:
        yield session


SesionAuth = Annotated[Session | None, Depends(sesion_si_auth)]


def _usuario_del_token(request: Request, db: Session, token: str) -> Usuario:
    """Decodifica el JWT, carga el usuario por id y lo deja anotado para los logs."""
    try:
        payload = decodificar_token(token)
    except jwt.InvalidTokenError as error:
        raise no_autorizado(MENSAJE_TOKEN_INVALIDO) from error

    sub = payload.get("sub")
    uid = payload.get("uid")
    huella = payload.get("pwd")
    if (
        not isinstance(sub, str)
        or not sub
        or not isinstance(uid, int)
        or isinstance(uid, bool)
        or uid <= 0
        or not isinstance(huella, str)
        or not huella
    ):
        raise no_autorizado(MENSAJE_TOKEN_INVALIDO)

    usuario = db.get(Usuario, uid)
    if usuario is None or usuario.usuario != sub:
        # Mismo mensaje que un token inválido: no se filtra si el usuario existe.
        raise no_autorizado(MENSAJE_TOKEN_INVALIDO)
    if not hmac.compare_digest(huella_password(usuario.password_hash), huella):
        # Cambió la contraseña, o se borró y recreó el usuario con el mismo id.
        raise no_autorizado(MENSAJE_TOKEN_INVALIDO)

    # El middleware de acceso toma estos valores para `logs_acceso`.
    request.state.credencial = "usuario"
    request.state.sujeto = usuario.usuario
    return usuario


def get_current_user(
    request: Request,
    db: SesionAuth,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Usuario | None:
    """Usuario del JWT de `Authorization: Bearer <jwt>`.

    Con `AUTH_REQUERIDA=0` devuelve None y las rutas de consulta quedan abiertas
    (desarrollo y pruebas). Con `AUTH_REQUERIDA=1` exige un token válido.
    """
    if not get_settings().auth_requerida:
        return None

    token = token_bearer(authorization)
    if not token:
        raise no_autorizado(MENSAJE_TOKEN_AUSENTE)
    if db is None:  # la dependencia perezosa solo devuelve None con la bandera apagada
        raise RuntimeError("No hay sesión de autenticación disponible.")
    return _usuario_del_token(request, db, token)


def get_current_user_stream(
    request: Request,
    token: Annotated[str | None, Query()] = None,
) -> Usuario | None:
    """Usuario del JWT que viaja en `?token=` (EventSource no manda headers).

    Abre una `SessionLocal` corta y la cierra antes de devolver: la conexión SSE
    puede durar minutos y no debe retener una sesión del pool de Postgres.
    """
    if not get_settings().auth_requerida:
        return None
    if not token:
        raise no_autorizado(MENSAJE_TOKEN_STREAM_AUSENTE)
    with SessionLocal(bind=get_engine()) as db:
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
