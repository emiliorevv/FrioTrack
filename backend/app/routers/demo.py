"""Endpoints de simulación para la demo: falla, puerta, ataque y recuperación.

Solo existen en el tenant demo y con `DEMO_HABILITADA=1`; el resto del mundo
recibe 404 aunque conozca las rutas. Nunca se exponen tokens de sensor: las
lecturas simuladas usan directamente `procesar_lectura`, como el tick del cron.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import RestauranteId, get_current_user
from app.db.base import utcnow
from app.db.models import (
    RESTAURANTE_DEMO_ID,
    Alerta,
    AlertaSeguridad,
    Camara,
    Sensor,
    Usuario,
)
from app.db.session import SessionLocal, get_db, get_engine
from app.erp.procesador import TIPO_ALERTA_TEMPERATURA
from app.routers.camaras import camara_del_restaurante
from app.schemas.demo import CamaraDemoEntrada, SimulacionOut
from app.schemas.operacion import AlertaSeguridadSalida, alerta_seguridad_salida
from app.schemas.telemetria import TelemetriaIn
from app.services.telemetria import procesar_lectura

logger = logging.getLogger(__name__)

ROLES_DEMO = frozenset({"dueno", "jefe_cocina"})
MENSAJE_NO_DISPONIBLE = "Demo no disponible."
MENSAJE_ROL = "Permisos insuficientes: se requiere rol dueno o jefe_cocina."

# Falla de compresor: 12 lecturas base y hasta 4 de refuerzo. Con la escala 30,
# el umbral de riesgo son 20 s reales; las primeras lecturas aún están en rango,
# así que el refuerzo garantiza que la alerta abra dentro de la misma tarea.
LECTURAS_FALLA = 12
LECTURAS_REFUERZO_FALLA = 4
INTERVALO_FALLA_S = 1.8
TEMPERATURA_INICIAL_FALLA = 1.0
PASO_FALLA_C = 0.4

# Puerta abierta en el congelador: umbral de 5 min / 30 = 10 s reales.
LECTURAS_PUERTA = 8
INTERVALO_PUERTA_S = 1.5
TEMPERATURA_CONGELADOR_C = -19.5

HUMEDAD_DEMO_PCT = 80.0

# Valores de la regla Sigma real `security/siem/fuerza-bruta-tokens.yml`.
REGLA_FUERZA_BRUTA_ID = "3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41"
REGLA_FUERZA_BRUTA = "Fuerza bruta de credenciales en la API"
IP_ATAQUE = "203.0.113.66"

# Una simulación activa por tipo; se libera en el `finally` de la tarea.
_activas: set[str] = set()
_cerrojo = threading.Lock()


def _demo_autorizado(
    usuario: Annotated[Usuario | None, Depends(get_current_user)],
    restaurante_id: RestauranteId,
) -> Usuario | None:
    """Gate de la demo: 404 fuera del tenant demo, 403 para roles sin permiso."""
    if not get_settings().demo_habilitada or restaurante_id != RESTAURANTE_DEMO_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MENSAJE_NO_DISPONIBLE)
    if usuario is not None and usuario.rol not in ROLES_DEMO:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MENSAJE_ROL)
    return usuario


router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(_demo_autorizado)])

Db = Annotated[Session, Depends(get_db)]


def _reservar(tipo: str) -> None:
    """Reserva una simulación; si ya hay una del mismo tipo, responde 409."""
    with _cerrojo:
        if tipo in _activas:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya hay una simulación de {tipo} en curso.",
            )
        _activas.add(tipo)


def _liberar(tipo: str) -> None:
    with _cerrojo:
        _activas.discard(tipo)


def _ejecutar(tipo: str, tarea: Callable[..., None], *args: object) -> None:
    """Corre la tarea en background y libera el registro pase lo que pase."""
    try:
        tarea(*args)
    finally:
        _liberar(tipo)


def _camara_entrada(datos: CamaraDemoEntrada | None, por_defecto: int) -> int:
    if datos is not None and datos.camara_id is not None:
        return datos.camara_id
    return por_defecto


def _sensor_activo(db: Session, camara_id: int) -> Sensor | None:
    return db.scalar(
        select(Sensor)
        .where(Sensor.camara_id == camara_id, Sensor.activo.is_(True))
        .order_by(Sensor.id)
        .limit(1)
    )


def _camara_y_sensor(db: Session, camara_id: int) -> tuple[Camara, Sensor]:
    """Valida cámara del tenant demo y sensor activo; 404/409 si no."""
    camara = camara_del_restaurante(db, camara_id, RESTAURANTE_DEMO_ID)
    sensor = _sensor_activo(db, camara.id)
    if sensor is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cámara no tiene un sensor activo; crea uno antes de simular.",
        )
    return camara, sensor


def _enviar_lectura(
    camara_id: int,
    sensor_id: str,
    temperatura_c: float,
    puerta_abierta: bool,
) -> tuple[str | None, bool]:
    """Envía una lectura con su propia sesión.

    Regresa `(estado_camara, hay_alerta_temperatura_abierta)`. La alerta es lo
    que decide si la falla ya cumplió su objetivo; el estado puede ser "alerta"
    solo por estar fuera de rango antes de que abra la alerta.
    """
    with SessionLocal(bind=get_engine()) as session:
        camara = session.get(Camara, camara_id, with_for_update=True)
        if camara is None:
            return None, False
        datos = TelemetriaIn(
            sensor_id=sensor_id,
            camara_id=camara_id,
            ts=utcnow(),
            temperatura_c=temperatura_c,
            humedad_pct=HUMEDAD_DEMO_PCT,
            puerta_abierta=puerta_abierta,
        )
        _, estado = procesar_lectura(session, datos, camara)
        alerta = session.scalar(
            select(Alerta.id)
            .where(
                Alerta.camara_id == camara_id,
                Alerta.tipo == TIPO_ALERTA_TEMPERATURA,
                Alerta.cerrada_en.is_(None),
            )
            .limit(1)
        )
        return estado, alerta is not None


def _simular_falla(camara_id: int, sensor_id: str) -> None:
    """Sube la temperatura 0.4 °C por lectura hasta que la alerta abra.

    Las 12 lecturas base empiezan en 1.0 °C; las primeras aún están en rango y
    el umbral de riesgo se mide desde la primera lectura fuera de rango. Si aun
    así no se abrió la alerta, se mandan hasta 4 lecturas de refuerzo para que
    la demo termine mostrándola.
    """
    total = LECTURAS_FALLA + LECTURAS_REFUERZO_FALLA
    for indice in range(total):
        temperatura = TEMPERATURA_INICIAL_FALLA + indice * PASO_FALLA_C
        try:
            estado, alerta_abierta = _enviar_lectura(
                camara_id,
                sensor_id,
                temperatura,
                False,
            )
        except Exception:
            logger.exception(
                "La simulación de falla no pudo enviar la lectura %s", indice
            )
            estado, alerta_abierta = None, False
        if estado is None:
            return
        if indice >= LECTURAS_FALLA - 1 and alerta_abierta:
            break
        if indice < total - 1:
            time.sleep(INTERVALO_FALLA_S)


def _simular_puerta(camara_id: int, sensor_id: str) -> None:
    """Mantiene la puerta abierta con la temperatura normal del congelador."""
    for indice in range(LECTURAS_PUERTA):
        try:
            _enviar_lectura(
                camara_id,
                sensor_id,
                TEMPERATURA_CONGELADOR_C,
                True,
            )
        except Exception:
            logger.exception(
                "La simulación de puerta no pudo enviar la lectura %s", indice
            )
        if indice < LECTURAS_PUERTA - 1:
            time.sleep(INTERVALO_PUERTA_S)


def _simular_recuperacion() -> None:
    """Manda una lectura normal a cada cámara demo para cerrar alertas."""
    objetivos: list[tuple[int, str, float]] = []
    with SessionLocal(bind=get_engine()) as session:
        camaras = list(
            session.scalars(
                select(Camara)
                .where(
                    Camara.restaurante_id == RESTAURANTE_DEMO_ID,
                    Camara.es_demo.is_(True),
                )
                .order_by(Camara.id)
            )
        )
        for camara in camaras:
            sensor = _sensor_activo(session, camara.id)
            if sensor is None:
                continue
            centro = (float(camara.rango_min_c) + float(camara.rango_max_c)) / 2
            objetivos.append((camara.id, sensor.id, centro))

    # Cada lectura abre su propia sesión y toma el lock de la cámara; hacerlo
    # dentro de la sesión anterior volvería a pedir el mismo lock.
    for camara_id, sensor_id, temperatura in objetivos:
        try:
            _enviar_lectura(camara_id, sensor_id, temperatura, False)
        except Exception:
            logger.exception(
                "La recuperación no pudo enviar la lectura a la cámara %s",
                camara_id,
            )


@router.post("/falla", response_model=SimulacionOut, status_code=status.HTTP_202_ACCEPTED)
def simular_falla(
    tareas: BackgroundTasks,
    db: Db,
    datos: CamaraDemoEntrada | None = None,
) -> SimulacionOut:
    """Programa una falla de compresor en la cámara indicada (default 1)."""
    camara, sensor = _camara_y_sensor(db, _camara_entrada(datos, 1))
    _reservar("falla")
    tareas.add_task(_ejecutar, "falla", _simular_falla, camara.id, sensor.id)
    return SimulacionOut(
        mensaje="Falla de compresor en curso.",
        camara_id=camara.id,
    )


@router.post("/puerta", response_model=SimulacionOut, status_code=status.HTTP_202_ACCEPTED)
def simular_puerta(
    tareas: BackgroundTasks,
    db: Db,
    datos: CamaraDemoEntrada | None = None,
) -> SimulacionOut:
    """Programa una puerta abierta en la cámara indicada (default 5)."""
    camara, sensor = _camara_y_sensor(db, _camara_entrada(datos, 5))
    _reservar("puerta")
    tareas.add_task(_ejecutar, "puerta", _simular_puerta, camara.id, sensor.id)
    return SimulacionOut(
        mensaje="Puerta abierta en curso.",
        camara_id=camara.id,
    )


@router.post("/ataque", response_model=AlertaSeguridadSalida, status_code=status.HTTP_201_CREATED)
def simular_ataque(db: Db) -> AlertaSeguridadSalida:
    """Inserta un hallazgo SIEM simulado de fuerza bruta; no bloquea ninguna IP."""
    alerta = AlertaSeguridad(
        regla_id=REGLA_FUERZA_BRUTA_ID,
        regla=REGLA_FUERZA_BRUTA,
        severidad="high",
        ts=utcnow(),
        ip_origen=IP_ATAQUE,
        detalle={
            "clave": f"ip:{IP_ATAQUE}",
            "intentos": 12,
            "ventana_s": 300,
            "rutas": ["/api/auth/login", "/api/telemetria"],
            "simulado": True,
        },
        accion="bloquear_ip",
    )
    db.add(alerta)
    db.commit()
    return alerta_seguridad_salida(alerta)


@router.post("/recuperar", response_model=SimulacionOut, status_code=status.HTTP_202_ACCEPTED)
def recuperar_demo(tareas: BackgroundTasks) -> SimulacionOut:
    """Manda lecturas normales a las cámaras demo para cerrar alertas."""
    _reservar("recuperar")
    tareas.add_task(_ejecutar, "recuperar", _simular_recuperacion)
    return SimulacionOut(mensaje="Recuperación en curso.")
