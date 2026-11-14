"""Servicio de ingesta de telemetría: persistencia y aplicación de reglas ERP."""

from __future__ import annotations

import hashlib
import hmac
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
from app.realtime.bus import bus
from app.schemas.operacion import alerta_salida, lote_salida
from app.schemas.telemetria import TelemetriaIn
from app.schemas.utils import iso


def _flotante(valor: Decimal | float | int | None) -> float | None:
    """Convierte un numeric de Postgres a float (o `None`)."""
    return None if valor is None else float(valor)


def _publicar_eventos(
    lectura: Lectura,
    camara: Camara,
    alertas_abiertas: list[Alerta],
    alertas_cerradas: list[Alerta],
    lotes_actualizados: list[Lote],
) -> None:
    """Publica en el bus los cambios ya confirmados en la base."""
    bus.publicar(
        "lectura",
        {
            "camara_id": lectura.camara_id,
            "ts": iso(lectura.ts),
            "temperatura_c": _flotante(lectura.temperatura_c),
            "humedad_pct": _flotante(lectura.humedad_pct),
            "puerta_abierta": lectura.puerta_abierta,
            "estado_camara": camara.estado,
        },
    )
    for alerta in alertas_abiertas:
        bus.publicar("alerta_abierta", alerta_salida(alerta).model_dump())
    for alerta in alertas_cerradas:
        bus.publicar("alerta_cerrada", alerta_salida(alerta).model_dump())
    for lote in lotes_actualizados:
        bus.publicar("lote_actualizado", lote_salida(lote).model_dump())


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


def _hash_token(token: str) -> str:
    """SHA-256 en hex del token: lo único que se guarda en `sensores.token_hash`."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validar_sensor(
    session: Session, sensor_id: str, camara_id: int, token: str
) -> None:
    """Autentica el token del sensor y comprueba que escriba en su propia cámara.

    Códigos del contrato: sensor inexistente o token incorrecto -> 401; sensor
    inactivo o de otra cámara -> 403. Los mensajes no distinguen cuál falló.
    """
    sensor = session.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sensor inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not sensor.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El sensor está inactivo.",
        )

    if not hmac.compare_digest(sensor.token_hash, _hash_token(token)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sensor inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if sensor.camara_id != camara_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El sensor no está autorizado para escribir en esa cámara.",
        )


def procesar_telemetria(
    session: Session, datos: TelemetriaIn, token: str
) -> tuple[int, str]:
    """Autentica el sensor y delega la ingesta de la lectura."""
    # El lock serializa contra el tick del cron: una lectura real que llega a
    # mitad del tick no se pierde ni la pisa una lectura de SIM-CRON.
    camara = session.get(Camara, datos.camara_id, with_for_update=True)
    if camara is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No existe la cámara {datos.camara_id}.",
        )

    _validar_sensor(session, datos.sensor_id, camara.id, token)
    return procesar_lectura(session, datos, camara)


def procesar_lectura(
    session: Session, datos: TelemetriaIn, camara: Camara
) -> tuple[int, str]:
    """Persiste una lectura, aplica las reglas ERP y regresa `(lectura_id, estado)`.

    No autentica: la cámara debe venir ya cargada (y bloqueada por quien escribe).
    Se llama después de validar el sensor o desde el tick del cron (`SIM-CRON`).
    """
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
    alertas_abiertas_nuevas: list[Alerta] = []
    alertas_cerradas: list[Alerta] = []

    alerta_temperatura = alertas_por_tipo.get(TIPO_ALERTA_TEMPERATURA)
    if resultado.cerrar_alerta_temperatura and alerta_temperatura is not None:
        alerta_temperatura.cerrada_en = ahora
        alertas_cerradas.append(alerta_temperatura)
    if resultado.abrir_alerta_temperatura:
        alerta_temperatura = Alerta(
            camara_id=camara.id,
            tipo=TIPO_ALERTA_TEMPERATURA,
            abierta_en=ahora,
            temperatura_max_c=resultado.temperatura_max_c,
            sms_enviados=0,  # SMS pendiente (fase posterior)
        )
        session.add(alerta_temperatura)
        alertas_abiertas_nuevas.append(alerta_temperatura)
    elif resultado.temperatura_max_c is not None and alerta_temperatura is not None:
        alerta_temperatura.temperatura_max_c = resultado.temperatura_max_c

    alerta_puerta = alertas_por_tipo.get(TIPO_ALERTA_PUERTA)
    if resultado.cerrar_alerta_puerta and alerta_puerta is not None:
        alerta_puerta.cerrada_en = ahora
        alertas_cerradas.append(alerta_puerta)
    if resultado.abrir_alerta_puerta:
        alerta_puerta = Alerta(
            camara_id=camara.id,
            tipo=TIPO_ALERTA_PUERTA,
            abierta_en=ahora,
            sms_enviados=0,  # SMS pendiente (fase posterior)
        )
        session.add(alerta_puerta)
        alertas_abiertas_nuevas.append(alerta_puerta)

    lotes_actualizados = [
        *resultado.lotes_a_recuperar,
        *resultado.lotes_a_riesgo,
        *resultado.lotes_a_merma,
    ]

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

    # Solo se publica lo que quedó confirmado; si el commit falla, nadie se entera.
    _publicar_eventos(
        lectura,
        camara,
        alertas_abiertas_nuevas,
        alertas_cerradas,
        lotes_actualizados,
    )
    return lectura.id, camara.estado
