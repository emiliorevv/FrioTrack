"""POST /api/auth/login: entrega el JWT de 8 h del dashboard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.config import get_settings
from app.core.auth import SesionDb, buscar_usuario, crear_token, no_autorizado
from app.core.rate_limit import LimitadorIntentos
from app.core.security import verify_password
from app.middleware.acceso import ip_de_scope
from app.schemas.auth import LoginEntrada, TokenSalida

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Un solo mensaje para usuario inexistente y contraseña incorrecta: el 401 no
# debe revelar cuál de los dos falló.
MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos."
MENSAJE_LIMITE = "Demasiados intentos de inicio de sesión; espera antes de reintentar."

# PBKDF2 precomputado de una contraseña dummy: verificar contra él cuando el
# usuario no existe iguala el tiempo de respuesta sin pagar el hash al importar.
HASH_SIN_USUARIO = (
    "pbkdf2_sha256$390000$e15f86256069ec4bff464335f7101430$"
    "160dd315f6fd9eb05a4f2b6a046694126fe8d410dadb01050eb3a168c288a3bf"
)

limitador_login = LimitadorIntentos()


@router.post("/login", response_model=TokenSalida)
def login(datos: LoginEntrada, request: Request, db: SesionDb) -> TokenSalida:
    """Valida las credenciales y firma el JWT del usuario.

    Siempre existe, con `AUTH_REQUERIDA` prendida o apagada: es la puerta de
    entrada del dashboard cuando la autenticación se active.
    """
    # La credencial se anota antes de validar para que un intento fallido quede
    # identificado en `logs_acceso`; el sujeto solo se registra al autenticar.
    request.state.credencial = "usuario"
    ip = ip_de_scope(request.scope) or "sin-ip"
    espera = limitador_login.permitir(ip)
    if espera:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=MENSAJE_LIMITE,
            headers={"Retry-After": str(espera)},
        )

    usuario = buscar_usuario(db, datos.usuario)
    hash_guardado = usuario.password_hash if usuario is not None else HASH_SIN_USUARIO
    if not verify_password(datos.password, hash_guardado) or usuario is None:
        raise no_autorizado(MENSAJE_CREDENCIALES)

    limitador_login.limpiar(ip)
    request.state.sujeto = usuario.usuario
    return TokenSalida(
        access_token=crear_token(usuario),
        expira_en_segundos=get_settings().jwt_expira_horas * 3600,
    )
