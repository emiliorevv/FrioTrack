"""`POST /api/auth/login` y `POST /api/auth/registro`: entregan el JWT del dashboard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.core.auth import SesionDb, buscar_usuario, crear_token, no_autorizado
from app.core.rate_limit import LimitadorIntentos
from app.core.security import hash_password, verify_password
from app.db.models import Restaurante, Usuario
from app.middleware.acceso import ip_de_scope
from app.schemas.auth import LoginEntrada, RegistroEntrada, TokenSalida

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Un solo mensaje para usuario inexistente y contraseña incorrecta: el 401 no
# debe revelar cuál de los dos falló.
MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos."
MENSAJE_LIMITE = "Demasiados intentos de inicio de sesión; espera antes de reintentar."
# Genérico a propósito: un 409 por usuario existente confirmaría una cuenta válida
# para atacarla en el login. La verificación por correo es la solución completa;
# mientras tanto, el rate limit y la regla SIEM de fuerza bruta cubren el abuso.
MENSAJE_REGISTRO_FALLIDO = "No se pudo completar el registro."
MENSAJE_LIMITE_REGISTRO = "Demasiados registros desde esta IP; espera antes de reintentar."

CONSTRAINT_USUARIO_UNICO = "usuarios_usuario_key"

# PBKDF2 precomputado de una contraseña dummy: verificar contra él cuando el
# usuario no existe iguala el tiempo de respuesta sin pagar el hash al importar.
HASH_SIN_USUARIO = (
    "pbkdf2_sha256$390000$e15f86256069ec4bff464335f7101430$"
    "160dd315f6fd9eb05a4f2b6a046694126fe8d410dadb01050eb3a168c288a3bf"
)

limitador_login = LimitadorIntentos()
# El alta es pública y crea filas: más estricta que el login para que un script
# no llene la tabla de restaurantes. Cuentan todos los intentos, también las
# altas exitosas: limpiar la ventana al registrar dejaría crear filas sin tope.
limitador_registro = LimitadorIntentos(maximo=5, ventana_seg=3600)


def _token_salida(usuario: Usuario) -> TokenSalida:
    """Arma la respuesta de login y registro con la misma expiración configurada."""
    return TokenSalida(
        access_token=crear_token(usuario),
        expira_en_segundos=get_settings().jwt_expira_horas * 3600,
    )


def _es_usuario_duplicado(error: IntegrityError) -> bool:
    """Solo la unicidad de `usuarios.usuario` es un duplicado esperado."""
    return (
        getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        == CONSTRAINT_USUARIO_UNICO
    )


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
    return _token_salida(usuario)


@router.post("/registro", response_model=TokenSalida, status_code=status.HTTP_201_CREATED)
def registro(datos: RegistroEntrada, request: Request, db: SesionDb) -> TokenSalida:
    """Crea un restaurante con su usuario dueño y entrega su JWT.

    Es público, con `AUTH_REQUERIDA` prendida o apagada: es la puerta de alta
    del producto. El restaurante nace sin cámaras; el dueño entra directo al
    dashboard con el token. Todavía no se verifica el correo (el identificador
    `usuario` puede ser el correo que escriba el usuario).
    """
    # Como en el login, la credencial queda anotada aunque el alta falle; el
    # sujeto solo se registra cuando el usuario existe.
    request.state.credencial = "registro"
    ip = ip_de_scope(request.scope) or "sin-ip"
    espera = limitador_registro.permitir(ip)
    if espera:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=MENSAJE_LIMITE_REGISTRO,
            headers={"Retry-After": str(espera)},
        )

    if buscar_usuario(db, datos.usuario) is not None:
        # Mismo mensaje y status que la carrera de unicidad: no se confirma si
        # el usuario existe, solo que el alta no procedió.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MENSAJE_REGISTRO_FALLIDO,
        )

    try:
        restaurante = Restaurante(nombre=datos.restaurante)
        db.add(restaurante)
        # El id del restaurante hace falta antes de crear al usuario.
        db.flush()
        usuario = Usuario(
            restaurante_id=restaurante.id,
            usuario=datos.usuario,
            password_hash=hash_password(datos.password),
            rol="dueno",
        )
        db.add(usuario)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # Solo la carrera por el mismo `usuario` es un duplicado esperado. Un
        # NOT NULL/FK/check se re-lanza: ocultarlo mandaría al cliente a
        # reintentar con otro nombre para siempre.
        if not _es_usuario_duplicado(error):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MENSAJE_REGISTRO_FALLIDO,
        ) from error

    request.state.sujeto = usuario.usuario
    return _token_salida(usuario)
