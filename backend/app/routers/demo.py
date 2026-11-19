"""Endpoints de simulación para la demo: falla, puerta, ataque y recuperación.

Solo existen en el tenant demo y se registran únicamente con
`DEMO_HABILITADA=1`; el resto del mundo recibe 404 aunque conozca las rutas.
Nunca se exponen tokens de sensor: las lecturas simuladas usan directamente
`procesar_lectura`, como el tick del cron.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth import DuenoOjefe, RestauranteId
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
from app.erp import reglas
from app.erp.procesador import TIPO_ALERTA_PUERTA, TIPO_ALERTA_TEMPERATURA
from app.routers.camaras import camara_del_restaurante
from app.schemas.demo import CamaraDemoEntrada, SimulacionOut
from app.schemas.operacion import AlertaSeguridadSalida, alerta_seguridad_salida
from app.schemas.telemetria import TelemetriaIn
from app.services.telemetria import procesar_lectura
from app.services.tick import ids_camaras_demo

logger = logging.getLogger(__name__)

MENSAJE_NO_DISPONIBLE = "Demo no disponible."

# Falla: las lecturas se calculan con el rango de la cámara. Se envían hasta que
# la alerta de temperatura abra o se agote el tiempo máximo (con margen sobre el
# umbral real de la cámara, que depende de ESCALA_TIEMPO).
INTERVALO_FALLA_S = 1.8
MAX_DURACION_FALLA_S = 60.0
MARGEN_FALLA_S = 20.0

# Puerta: la alerta es por tiempo (5 min / escala). El paso de temperatura se
# calcula para que en LECTURAS_PUERTA lecturas la última quede bajo el máximo.
LECTURAS_PUERTA = 8
INTERVALO_PUERTA_S = 1.5
MINUTOS_ALERTA_PUERTA = 5.0
MAX_DURACION_PUERTA_S = 60.0
MARGEN_PUERTA_S = 15.0

HUMEDAD_DEMO_PCT = 80.0
EXPIRACION_SIMULACION_S = 120.0
ESPERA_CANCELACION_S = 10.0

# Valores de la regla Sigma real `security/siem/fuerza-bruta-tokens.yml`.
REGLA_FUERZA_BRUTA_ID = "3b8e2f6a-9c41-4d7e-8a15-2f6c0d9e7b41"
REGLA_FUERZA_BRUTA = "Fuerza bruta de credenciales en la API"
IP_ATAQUE = "203.0.113.66"


@dataclass
class _Simulacion:
    """Slot activo: una sola simulación por cámara (o una recuperación)."""

    tipo: str
    camara_id: int | None
    cancelar: threading.Event
    terminada: threading.Event
    iniciada_en: float


# La clave es la cámara para falla/puerta y "recuperar" para la recuperación:
# no se pueden pisar una falla y una puerta en la misma cámara. El timestamp
# permite liberar slots vencidos aunque Starlette no ejecute la tarea.
_activas: dict[int | str, _Simulacion] = {}
_cerrojo = threading.Lock()


def _demo_autorizado(
    usuario: DuenoOjefe,
    restaurante_id: RestauranteId,
) -> Usuario | None:
    """Solo el tenant demo; los roles los exige `DuenoOjefe`.

    Con `DEMO_HABILITADA=0` el router ni siquiera se registra en `create_app`,
    así que la ruta responde 404 sin pasar por autenticación.
    """
    if restaurante_id != RESTAURANTE_DEMO_ID:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=MENSAJE_NO_DISPONIBLE,
        )
    return usuario


router = APIRouter(prefix="/api/demo", tags=["demo"], dependencies=[Depends(_demo_autorizado)])

Db = Annotated[Session, Depends(get_db)]


def _clave_simulacion(tipo: str, camara_id: int | None) -> int | str:
    return "recuperar" if tipo == "recuperar" or camara_id is None else camara_id


def _reservar(tipo: str, camara_id: int | None) -> _Simulacion:
    """Reserva la cámara (o la recuperación) y responde 409 si ya está ocupada.

    Una sola simulación por cámara: falla y puerta no pueden correr a la vez en
    la misma cámara. La recuperación usa su propia clave y cancela a las demás.
    """
    ahora = time.monotonic()
    clave = _clave_simulacion(tipo, camara_id)
    with _cerrojo:
        vencidas = [
            nombre
            for nombre, simulacion in _activas.items()
            if ahora - simulacion.iniciada_en > EXPIRACION_SIMULACION_S
        ]
        for nombre in vencidas:
            simulacion = _activas.pop(nombre)
            simulacion.cancelar.set()
            simulacion.terminada.set()

        activa = _activas.get(clave)
        if activa is not None:
            detalle = (
                f"La cámara {camara_id} ya tiene una simulación de "
                f"{activa.tipo} en curso."
                if clave != "recuperar"
                else "Ya hay una recuperación en curso."
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detalle,
            )

        simulacion = _Simulacion(
            tipo=tipo,
            camara_id=camara_id,
            cancelar=threading.Event(),
            terminada=threading.Event(),
            iniciada_en=ahora,
        )
        _activas[clave] = simulacion
        return simulacion


def _liberar(simulacion: _Simulacion) -> None:
    """Suelta el slot solo si sigue siendo el mismo (no pisa una simulación nueva)."""
    clave = _clave_simulacion(simulacion.tipo, simulacion.camara_id)
    with _cerrojo:
        if _activas.get(clave) is simulacion:
            _activas.pop(clave, None)
    simulacion.terminada.set()


def _ejecutar(simulacion: _Simulacion, tarea: Callable[..., None], *args: object) -> None:
    """Corre la tarea en background y libera el registro pase lo que pase."""
    try:
        tarea(*args)
    finally:
        _liberar(simulacion)


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
    """Valida cámara del tenant demo, marcada `es_demo`, y su sensor activo."""
    camara = camara_del_restaurante(db, camara_id, RESTAURANTE_DEMO_ID)
    if not camara.es_demo:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cámara no es de la demo; usa una cámara del seed.",
        )
    sensor = _sensor_activo(db, camara.id)
    if sensor is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cámara no tiene un sensor activo; crea uno antes de simular.",
        )
    return camara, sensor


def _rango(camara: Camara) -> tuple[float, float]:
    return float(camara.rango_min_c), float(camara.rango_max_c)


def _base_y_paso_falla(camara: Camara) -> tuple[float, float]:
    """Serie relativa al rango: la segunda lectura ya cruza el máximo."""
    rango_min, rango_max = _rango(camara)
    ancho = rango_max - rango_min
    base = rango_max - min(0.2, ancho * 0.1)
    paso = max(0.4, ancho * 0.2)
    return base, paso


def _base_y_paso_puerta(camara: Camara) -> tuple[float, float]:
    """Centro del rango y paso pequeño para LECTURAS_PUERTA lecturas.

    La última lectura de esa secuencia queda por debajo de `rango_max_c`, así
    que la puerta no dispara una alerta de temperatura; la alerta es por tiempo.
    """
    rango_min, rango_max = _rango(camara)
    base = (rango_min + rango_max) / 2
    margen = (rango_max - rango_min) / 2
    paso = min(0.2, margen / LECTURAS_PUERTA)
    return base, paso


def _temperatura_centro(camara: Camara) -> float:
    """Punto medio del rango; para la recuperación."""
    rango_min, rango_max = _rango(camara)
    return (rango_min + rango_max) / 2


def _enviar_lectura(
    camara_id: int,
    sensor_id: str,
    temperatura_c: float,
    puerta_abierta: bool,
) -> tuple[str | None, set[str]]:
    """Envía una lectura con su propia sesión.

    Regresa `(estado_camara, tipos_de_alerta_abiertos)`. La alerta es lo que
    decide si una simulación ya cumplió su objetivo; el estado puede ser
    "alerta" solo por estar fuera de rango antes de que abra la alerta.
    """
    with SessionLocal(bind=get_engine()) as session:
        camara = session.get(Camara, camara_id, with_for_update=True)
        if camara is None:
            return None, set()
        datos = TelemetriaIn(
            sensor_id=sensor_id,
            camara_id=camara_id,
            ts=utcnow(),
            temperatura_c=temperatura_c,
            humedad_pct=HUMEDAD_DEMO_PCT,
            puerta_abierta=puerta_abierta,
        )
        _, estado = procesar_lectura(session, datos, camara)
        alertas = set(
            session.scalars(
                select(Alerta.tipo).where(
                    Alerta.camara_id == camara_id,
                    Alerta.cerrada_en.is_(None),
                )
            )
        )
        return estado, alertas


def _simular_falla(
    camara_id: int,
    sensor_id: str,
    base: float,
    paso: float,
    min_para_riesgo: int,
    cancelar: threading.Event,
) -> None:
    """Sube la temperatura hasta que abra la alerta o se agote el tiempo máximo.

    El máximo cubre al menos 60 s y deja 20 s de margen sobre el umbral real de
    la cámara (`min_para_riesgo` escalado); si la alerta no abre en ese plazo,
    la simulación termina sin colgar el slot.
    """
    escala = get_settings().escala_tiempo
    umbral = reglas.segundos_efectivos(min_para_riesgo, escala)
    limite = max(MAX_DURACION_FALLA_S, umbral + MARGEN_FALLA_S)
    inicio = time.monotonic()
    indice = 0

    while time.monotonic() - inicio < limite:
        if cancelar.is_set():
            return
        temperatura = base + paso * indice
        try:
            estado, alertas = _enviar_lectura(
                camara_id,
                sensor_id,
                temperatura,
                False,
            )
        except Exception:
            logger.exception(
                "La simulación de falla no pudo enviar la lectura %s; reintenta",
                indice,
            )
            if cancelar.wait(0.2):
                return
            try:
                estado, alertas = _enviar_lectura(
                    camara_id,
                    sensor_id,
                    temperatura,
                    False,
                )
            except Exception:
                logger.exception(
                    "La simulación de falla sigue fallando en la lectura %s",
                    indice,
                )
                indice += 1
                if cancelar.wait(INTERVALO_FALLA_S):
                    return
                continue

        if estado is None:
            return
        if TIPO_ALERTA_TEMPERATURA in alertas:
            return
        indice += 1
        if cancelar.wait(INTERVALO_FALLA_S):
            return


def _simular_puerta(
    camara_id: int,
    sensor_id: str,
    temperatura_inicial: float,
    paso: float,
    temperatura_maxima: float,
    cancelar: threading.Event,
) -> None:
    """Mantiene la puerta abierta hasta que abra su alerta o venza el máximo.

    La temperatura sube poco a poco y se topa en `temperatura_maxima` (0.1 °C
    bajo el máximo): la alerta protagonista es la de puerta, que es por tiempo.
    El loop deja margen para reintentar si una lectura falla.
    """
    escala = get_settings().escala_tiempo
    umbral = reglas.segundos_efectivos(MINUTOS_ALERTA_PUERTA, escala)
    limite = min(MAX_DURACION_PUERTA_S, umbral + MARGEN_PUERTA_S)
    inicio = time.monotonic()
    indice = 0

    while time.monotonic() - inicio < limite:
        if cancelar.is_set():
            return
        temperatura = min(
            round(temperatura_inicial + paso * indice, 1),
            temperatura_maxima,
        )
        try:
            estado, alertas = _enviar_lectura(
                camara_id,
                sensor_id,
                temperatura,
                True,
            )
        except Exception:
            logger.exception(
                "La simulación de puerta no pudo enviar la lectura %s; reintenta",
                indice,
            )
            if cancelar.wait(0.2):
                return
            continue

        if estado is None:
            return
        if TIPO_ALERTA_PUERTA in alertas:
            return
        indice += 1
        if cancelar.wait(INTERVALO_PUERTA_S):
            return


def _cancelar_simulaciones() -> None:
    """Pide a falla/puerta que terminen y espera (con timeout) a que lo hagan."""
    with _cerrojo:
        activas = [
            simulacion
            for simulacion in _activas.values()
            if simulacion.tipo in ("falla", "puerta")
        ]
        for simulacion in activas:
            simulacion.cancelar.set()
    for simulacion in activas:
        simulacion.terminada.wait(timeout=ESPERA_CANCELACION_S)


def _simular_recuperacion() -> None:
    """Cancela falla/puerta y manda una lectura normal a cada cámara demo."""
    _cancelar_simulaciones()

    objetivos: list[tuple[int, str, float]] = []
    with SessionLocal(bind=get_engine()) as session:
        ids = ids_camaras_demo(session)
        camaras = (
            list(
                session.scalars(
                    select(Camara).where(Camara.id.in_(ids)).order_by(Camara.id)
                )
            )
            if ids
            else []
        )
        for camara in camaras:
            sensor = _sensor_activo(session, camara.id)
            if sensor is None:
                continue
            objetivos.append((camara.id, sensor.id, _temperatura_centro(camara)))

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
    """Programa una falla de compresor en una cámara demo (default 1)."""
    camara, sensor = _camara_y_sensor(db, _camara_entrada(datos, 1))
    base, paso = _base_y_paso_falla(camara)
    simulacion = _reservar("falla", camara.id)
    tareas.add_task(
        _ejecutar,
        simulacion,
        _simular_falla,
        camara.id,
        sensor.id,
        base,
        paso,
        camara.min_para_riesgo,
        simulacion.cancelar,
    )
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
    """Programa una puerta abierta en una cámara demo (default 5).

    La temperatura sube desde el centro del rango con un paso pequeño para que
    se note, pero la última lectura queda por debajo del máximo: la alerta que
    abre es la de puerta, no una de temperatura.
    """
    camara, sensor = _camara_y_sensor(db, _camara_entrada(datos, 5))
    base, paso = _base_y_paso_puerta(camara)
    simulacion = _reservar("puerta", camara.id)
    tareas.add_task(
        _ejecutar,
        simulacion,
        _simular_puerta,
        camara.id,
        sensor.id,
        base,
        paso,
        float(camara.rango_max_c) - 0.1,
        simulacion.cancelar,
    )
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
    """Cancela falla/puerta y manda lecturas normales a las cámaras demo."""
    simulacion = _reservar("recuperar", None)
    tareas.add_task(_ejecutar, simulacion, _simular_recuperacion)
    return SimulacionOut(mensaje="Recuperación en curso.")
