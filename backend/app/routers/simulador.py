"""Endpoint del tick que dispara el Cloudflare Worker cada minuto."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.schemas.simulador import TickOut
from app.services.tick import SENSOR_CRON, ejecutar_tick

router = APIRouter(prefix="/api/simulador", tags=["simulador"])

SesionDB = Annotated[Session, Depends(get_db)]
Autorizacion = Annotated[str | None, Header(alias="Authorization")]

PREFIJO_BEARER = "Bearer "
MENSAJE_TOKEN_INVALIDO = (
    "Token de cron ausente o inválido: usa `Authorization: Bearer <token_cron>`."
)


def _validar_token(authorization: str | None) -> None:
    """Comprueba `Authorization: Bearer <token_cron>` contra `CRON_TOKEN`.

    El token nunca se registra ni se incluye en los mensajes de error. Sin
    token, mal formado, incorrecto o sin `CRON_TOKEN` configurado -> 401.
    """
    token = ""
    if authorization and authorization.startswith(PREFIJO_BEARER):
        token = authorization.removeprefix(PREFIJO_BEARER).strip()

    esperado = get_settings().cron_token
    if not token or not esperado or not hmac.compare_digest(
        token.encode("utf-8"), esperado.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=MENSAJE_TOKEN_INVALIDO,
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/tick", status_code=status.HTTP_202_ACCEPTED, response_model=TickOut)
def ejecutar_tick_cron(
    request: Request,
    session: SesionDB,
    authorization: Autorizacion = None,
) -> TickOut:
    """Genera lecturas normales para las cámaras que no tienen datos frescos."""
    # Antes de validar el token: un 401 debe conservar la credencial y el sujeto
    # para la regla SIEM de fuerza bruta, igual que en `POST /telemetria`.
    request.state.credencial = "cron"
    request.state.sujeto = SENSOR_CRON
    _validar_token(authorization)
    lecturas, saltadas = ejecutar_tick(session)
    return TickOut(lecturas=lecturas, saltadas=saltadas)
