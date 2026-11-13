"""Servicio de ingesta de telemetría: persistencia y aplicación de reglas ERP."""

from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import utcnow
from app.db.models import Alerta, Camara, Lectura, Lote, Sensor
from app.erp import reglas
from app.erp.procesador import (
    TIPO_ALERTA_PUERTA,
    TIPO_ALERTA_TEMPERATURA,
    evaluar_lectura,
)
from app.schemas.telemetria import TelemetriaIn


def _cargar_lotes(session: Session, camara_id: int) -> list[Lote]:
    """Lotes de la cámara, en cualquier estado."""
    return list(session.scalars(select(Lote).where(Lote.camara_id == camara_id)))


def _cargar_alertas_abiertas(session: Session, camara_id: int) -> list[Alerta]:
    """Alertas de la cámara todavía sin cerrar (una por tipo como máximo)."""
    return list(
        session.scalars(
            select(Alerta).where(
                Alerta.camara_id == camara_id, Alerta.cerrada_en.is_(None)
            )
        )
    )


def _validar_sensor(session: Session, sensor_id: str, camara_id: int) -> None:
    """Comprueba que el sensor exista, esté activo y pertenezca a la cámara."""
    sensor = session.get(Sensor, sensor_id)
    # Auth pendiente (fase posterior): aquí irá la comparación del token y el
    # hash SHA-256; por ahora basta con que el sensor exista y sea de la cámara.
    if sensor is None or not sensor.activo or sensor.camara_id != camara_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El sensor no está autorizado para escribir en esa cámara.",
        )


def procesar_telemetria(
    session: Session, datos: TelemetriaIn
) -> tuple[int, str]:
    """Persiste una lectura, aplica las reglas ERP y regresa `(lectura_id, estado)`."""
    camara = session.get(Camara, datos.camara_id)
    if camara is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la cámara {datos.camara_id}.",
        )

    _validar_sensor(session, datos.sensor_id, camara.id)

    ahora = utcnow()
    lectura = Lectura(
        camara_id=camara.id,
        sensor_id=datos.sensor_id,
        ts=datos.ts,
        recibida_en=ahora,
        temperatura_c=Decimal(str(datos.temperatura_c)),
        humedad_pct=Decimal(str(datos.humedad_pct)),
        puerta_abierta=datos.puerta_abierta,
        sospechosa=False,
    )
    session.add(lectura)
    session.flush()  # asigna lectura.id

    # Las ventanas de tiempo se actualizan con esta lectura ANTES de evaluar:
    # así una salida de rango que empieza aquí todavía no acumula tiempo.
    en_rango = reglas.esta_en_rango(
        datos.temperatura_c,
        float(camara.rango_min_c),
        float(camara.rango_max_c),
    )
    if en_rango:
        camara.fuera_de_rango_desde = None
    elif camara.fuera_de_rango_desde is None:
        camara.fuera_de_rango_desde = ahora

    if datos.puerta_abierta:
        if camara.puerta_abierta_desde is None:
            camara.puerta_abierta_desde = ahora
    else:
        camara.puerta_abierta_desde = None

    camara.ultima_lectura_id = lectura.id

    lotes = _cargar_lotes(session, camara.id)
    alertas_abiertas = _cargar_alertas_abiertas(session, camara.id)
    resultado = evaluar_lectura(
        camara=camara,
        temperatura_c=datos.temperatura_c,
        puerta_abierta=datos.puerta_abierta,
        ahora=ahora,
        escala=get_settings().escala_tiempo,
        lotes=lotes,
        alertas_abiertas=alertas_abiertas,
    )

    alertas_por_tipo = {alerta.tipo: alerta for alerta in alertas_abiertas}

    alerta_temperatura = alertas_por_tipo.get(TIPO_ALERTA_TEMPERATURA)
    if resultado.cerrar_alerta_temperatura and alerta_temperatura is not None:
        alerta_temperatura.cerrada_en = ahora
    if resultado.abrir_alerta_temperatura:
        session.add(
            Alerta(
                camara_id=camara.id,
                tipo=TIPO_ALERTA_TEMPERATURA,
                abierta_en=ahora,
                temperatura_max_c=resultado.temperatura_max_c,
                sms_enviados=0,  # SMS pendiente (fase posterior)
            )
        )
    elif resultado.temperatura_max_c is not None and alerta_temperatura is not None:
        alerta_temperatura.temperatura_max_c = resultado.temperatura_max_c

    alerta_puerta = alertas_por_tipo.get(TIPO_ALERTA_PUERTA)
    if resultado.cerrar_alerta_puerta and alerta_puerta is not None:
        alerta_puerta.cerrada_en = ahora
    if resultado.abrir_alerta_puerta:
        session.add(
            Alerta(
                camara_id=camara.id,
                tipo=TIPO_ALERTA_PUERTA,
                abierta_en=ahora,
                sms_enviados=0,  # SMS pendiente (fase posterior)
            )
        )

    for lote in resultado.lotes_a_recuperar:
        lote.estado = "ok"
    for lote in resultado.lotes_a_riesgo:
        lote.estado = "en_riesgo"
    for lote in resultado.lotes_a_merma:
        lote.estado = "merma"
        lote.merma_en = ahora

    camara.estado = reglas.estado_camara(
        en_rango=en_rango,
        puerta_abierta=datos.puerta_abierta,
        lotes_en_riesgo=sum(1 for lote in lotes if lote.estado == "en_riesgo"),
        lotes_en_merma=sum(1 for lote in lotes if lote.estado == "merma"),
    )

    session.commit()
    return lectura.id, camara.estado
