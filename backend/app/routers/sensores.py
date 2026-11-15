"""CRUD de sensores: alta con token, rotación, activación y baja."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import RestauranteId, get_current_user, require_rol
from app.core.sensor_token import generar_token, hash_token
from app.db.models import Camara, Lectura, Sensor, Usuario
from app.db.session import get_db
from app.routers.camaras import camara_del_restaurante
from app.schemas.sensores import (
    SensorActualizacion,
    SensorConTokenSalida,
    SensorCreacion,
    SensorListaSalida,
    SensorSalida,
)
from app.schemas.utils import iso

router = APIRouter(prefix="/api", tags=["sensores"], dependencies=[Depends(get_current_user)])

Db = Annotated[Session, Depends(get_db)]
Dueno = Annotated[Usuario | None, Depends(require_rol("dueno"))]

MENSAJE_SENSOR_CON_LECTURAS = (
    "El sensor tiene lecturas asociadas; desactívalo en lugar de eliminarlo."
)


def sensor_del_restaurante(
    db: Session,
    sensor_id: str,
    restaurante_id: int,
) -> Sensor:
    """Carga el sensor o responde 404 si no existe o su cámara es de otro tenant."""
    sensor = db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="Sensor no encontrado")
    camara_del_restaurante(
        db,
        sensor.camara_id,
        restaurante_id,
        detalle="Sensor no encontrado",
    )
    return sensor


def _salida_sensor(sensor: Sensor) -> SensorSalida:
    """Sensor sin `token_hash`: el hash nunca sale de la base."""
    return SensorSalida(
        id=sensor.id,
        camara_id=sensor.camara_id,
        activo=sensor.activo,
    )


def _id_libre(db: Session) -> str:
    """Genera `S-` + 8 hex y comprueba que la PK siga libre."""
    for _ in range(10):
        ident = f"S-{secrets.token_hex(4)}"
        if db.get(Sensor, ident) is None:
            return ident
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="No se pudo generar un id único para el sensor; reintenta.",
    )


def _token_nuevo(sensor: Sensor) -> str:
    """Asigna un token nuevo al sensor y regresa el valor en claro una sola vez."""
    token = generar_token()
    sensor.token_hash = hash_token(token)
    return token


@router.get("/sensores", response_model=list[SensorListaSalida])
def listar_sensores(db: Db, restaurante_id: RestauranteId) -> list[SensorListaSalida]:
    """Lista los sensores del restaurante con su cámara y la última lectura.

    Son dos consultas: sensores con el nombre de su cámara y un agregado
    `max(recibida_en)` por sensor. Nunca se hace una consulta por sensor ni se
    expone `token_hash`.
    """
    filas = db.execute(
        select(Sensor, Camara.nombre)
        .join(Camara, Camara.id == Sensor.camara_id)
        .where(Camara.restaurante_id == restaurante_id)
        .order_by(Sensor.id)
    ).all()
    ultimas = dict(
        db.execute(
            select(Lectura.sensor_id, func.max(Lectura.recibida_en))
            .join(Camara, Camara.id == Lectura.camara_id)
            .where(Camara.restaurante_id == restaurante_id)
            .group_by(Lectura.sensor_id)
        ).all()
    )

    return [
        SensorListaSalida(
            id=sensor.id,
            camara_id=sensor.camara_id,
            activo=sensor.activo,
            camara_nombre=camara_nombre,
            ultima_lectura=iso(ultimas.get(sensor.id)),
        )
        for sensor, camara_nombre in filas
    ]


@router.post(
    "/camaras/{camara_id}/sensores",
    response_model=SensorConTokenSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_sensor(
    camara_id: int,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: Dueno,
    datos: SensorCreacion | None = None,
) -> SensorConTokenSalida:
    """Crea un sensor para una cámara del tenant y entrega su token una sola vez."""
    camara = camara_del_restaurante(db, camara_id, restaurante_id)
    if datos is not None and datos.id is not None:
        if db.get(Sensor, datos.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="El sensor ya existe."
            )
        ident = datos.id
    else:
        ident = _id_libre(db)

    token = generar_token()
    sensor = Sensor(
        id=ident,
        camara_id=camara.id,
        token_hash=hash_token(token),
        activo=True,
    )
    db.add(sensor)
    try:
        db.commit()
    except IntegrityError as error:
        # Carrera con otro alta del mismo id (la PK es lo único que puede chocar).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El sensor ya existe.",
        ) from error
    return SensorConTokenSalida(sensor=_salida_sensor(sensor), token=token)


@router.post("/sensores/{sensor_id}/rotar-token", response_model=SensorConTokenSalida)
def rotar_token(
    sensor_id: str,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: Dueno,
) -> SensorConTokenSalida:
    """Reemplaza el hash del token; el token anterior deja de autenticar al instante."""
    sensor = sensor_del_restaurante(db, sensor_id, restaurante_id)
    token = _token_nuevo(sensor)
    db.commit()
    return SensorConTokenSalida(sensor=_salida_sensor(sensor), token=token)


@router.patch("/sensores/{sensor_id}", response_model=SensorSalida)
def actualizar_sensor(
    sensor_id: str,
    datos: SensorActualizacion,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: Dueno,
) -> SensorSalida:
    """Activa o desactiva el sensor; desactivado, `POST /telemetria` responde 403."""
    sensor = sensor_del_restaurante(db, sensor_id, restaurante_id)
    sensor.activo = datos.activo
    db.commit()
    return _salida_sensor(sensor)


@router.delete("/sensores/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_sensor(
    sensor_id: str,
    db: Db,
    restaurante_id: RestauranteId,
    usuario: Dueno,
) -> Response:
    """Elimina un sensor sin lecturas; con historial se sugiere desactivarlo."""
    sensor = sensor_del_restaurante(db, sensor_id, restaurante_id)
    lecturas = db.scalar(
        select(func.count()).select_from(Lectura).where(Lectura.sensor_id == sensor.id)
    )
    if lecturas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MENSAJE_SENSOR_CON_LECTURAS,
        )
    db.delete(sensor)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
