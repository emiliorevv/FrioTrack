"""Endpoint de ingesta de telemetría."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.telemetria import TelemetriaIn, TelemetriaOut
from app.services.telemetria import procesar_telemetria

router = APIRouter(prefix="/api", tags=["telemetria"])

SesionDB = Annotated[Session, Depends(get_db)]


@router.post(
    "/telemetria",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TelemetriaOut,
)
def recibir_telemetria(
    datos: TelemetriaIn,
    session: SesionDB,
) -> TelemetriaOut:
    """Recibe una lectura de un sensor, la guarda y aplica las reglas del ERP.

    Auth pendiente (fase posterior): el contrato pedirá `Bearer <token_sensor>`;
    por ahora la pertenencia sensor-cámara se valida en el servicio.
    """
    lectura_id, estado_camara = procesar_telemetria(session, datos)
    return TelemetriaOut(lectura_id=lectura_id, estado_camara=estado_camara)
