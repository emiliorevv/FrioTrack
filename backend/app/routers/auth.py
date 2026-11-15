"""POST /api/auth/login: entrega el JWT de 8 h del dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import crear_token
from app.core.security import hash_password, verify_password
from app.db.models import Usuario
from app.db.session import get_db
from app.schemas.auth import LoginEntrada, TokenSalida

router = APIRouter(prefix="/api/auth", tags=["auth"])

SesionDb = Annotated[Session, Depends(get_db)]

# Un solo mensaje para usuario inexistente y contraseña incorrecta: el 401 no
# debe revelar cuál de los dos falló.
MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos."

# Hash de descarte: verificar contra él cuando el usuario no existe mantiene un
# tiempo de respuesta parecido y cierra la enumeración de usuarios por latencia.
HASH_SIN_USUARIO = hash_password("usuario-inexistente")


@router.post("/login", response_model=TokenSalida)
def login(datos: LoginEntrada, request: Request, db: SesionDb) -> TokenSalida:
    """Valida las credenciales y firma el JWT del usuario.

    Siempre existe, con `AUTH_REQUERIDA` prendida o apagada: es la puerta de
    entrada del dashboard cuando la autenticación se active.
    """
    # Igual que en telemetría y cron: la credencial se anota antes de validar
    # para que un intento fallido también quede identificado en `logs_acceso`.
    request.state.credencial = "usuario"
    request.state.sujeto = datos.usuario

    usuario = db.scalar(select(Usuario).where(Usuario.usuario == datos.usuario))
    hash_guardado = usuario.password_hash if usuario is not None else HASH_SIN_USUARIO
    if not verify_password(datos.password, hash_guardado) or usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=MENSAJE_CREDENCIALES,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenSalida(
        access_token=crear_token(usuario.usuario, usuario.rol),
        expira_en_segundos=get_settings().jwt_expira_horas * 3600,
    )
