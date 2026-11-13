"""Endpoint de ingesta de telemetría."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.telemetria import TelemetriaIn, TelemetriaOut
from app.services.telemetria import procesar_telemetria

router = APIRouter(prefix="/api", tags=["telemetria"])

SesionDB = Annotated[Session, Depends(get_db)]
Autorizacion = Annotated[str | None, Header(alias="Authorization")]

PREFIJO_BEARER = "Bearer "
MENSAJE_TOKEN_AUSENTE = (
    "Token de sensor ausente o mal formado: usa `Authorization: Bearer <token_sensor>`."
)


def _token_de_sensor(authorization: str | None) -> str:
    """Extrae el token de `Authorization: Bearer <token>`.

    El token nunca se registra ni se incluye en los mensajes de error: solo se
    pasa al servicio, que compara su SHA-256 contra `sensores.token_hash`.
    """
    token = ""
    if authorization and authorization.startswith(PREFIJO_BEARER):
        token = authorization.removeprefix(PREFIJO_BEARER).strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=MENSAJE_TOKEN_AUSENTE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


@router.post(
    "/telemetria",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TelemetriaOut,
)
def recibir_telemetria(
    datos: TelemetriaIn,
    session: SesionDB,
    authorization: Autorizacion = None,
) -> TelemetriaOut:
    """Recibe una lectura autenticada con el token de su sensor.

    El contrato pide un token por sensor (`Authorization: Bearer <token_sensor>`).
    El JWT de usuario del dashboard sigue diferido a la fase de consulta.
    """
    token = _token_de_sensor(authorization)
    lectura_id, estado_camara = procesar_telemetria(session, datos, token=token)
    return TelemetriaOut(lectura_id=lectura_id, estado_camara=estado_camara)
