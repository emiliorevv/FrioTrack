"""Cálculo de los KPIs del dashboard: SQL agregado más las funciones puras.

Vive fuera del router para que `GET /api/kpis` y el evento periódico del stream
compartan exactamente las mismas queries.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import Alerta, Camara, Lectura, Lote
from app.erp.kpis import merma_en_periodo, pct_en_rango, promedio_respuesta_min, valor_en_riesgo


def _ahora() -> datetime:
    """Reloj del proceso; las pruebas lo reemplazan para fijar fechas."""
    return datetime.now(UTC)


def _consulta_pct_en_rango(desde: datetime, restaurante_id: int) -> Select[tuple[int, int]]:
    """Cuenta lecturas totales y lecturas dentro de rango desde `desde`, en SQL.

    `count(*) FILTER (...)` compila en Postgres y evita traer las lecturas a
    Python; los extremos cuentan como dentro de rango, igual que antes. El join
    con la cámara aplica el aislamiento por restaurante: `lecturas` no guarda
    tenant propio.
    """
    dentro = func.count().filter(
        Lectura.temperatura_c.between(Camara.rango_min_c, Camara.rango_max_c)
    )
    return (
        select(func.count(), dentro)
        .select_from(Lectura)
        .join(Camara, Camara.id == Lectura.camara_id)
        .where(
            Lectura.recibida_en >= desde,
            Camara.restaurante_id == restaurante_id,
        )
    )


def calcular_kpis(db: Session, restaurante_id: int) -> dict[str, Any]:
    """Calcula los seis KPIs del restaurante con las queries actuales."""
    ahora = _ahora()
    desde = ahora - timedelta(hours=24)

    total_lecturas, lecturas_en_rango = db.execute(
        _consulta_pct_en_rango(desde, restaurante_id)
    ).one()

    alertas_activas = db.scalar(
        select(func.count())
        .select_from(Alerta)
        .join(Camara, Camara.id == Alerta.camara_id)
        .where(
            Alerta.cerrada_en.is_(None),
            Camara.restaurante_id == restaurante_id,
        )
    )

    atendidas = db.execute(
        select(Alerta.abierta_en, Alerta.atendida_en)
        .join(Camara, Camara.id == Alerta.camara_id)
        .where(
            Alerta.atendida_en.is_not(None),
            Camara.restaurante_id == restaurante_id,
        )
    ).all()

    costos_en_riesgo = db.scalars(
        select(Lote.costo_total_mxn)
        .join(Camara, Camara.id == Lote.camara_id)
        .where(
            Lote.estado == "en_riesgo",
            Camara.restaurante_id == restaurante_id,
        )
    ).all()

    mermas = db.execute(
        select(Lote.merma_en, Lote.costo_total_mxn)
        .join(Camara, Camara.id == Lote.camara_id)
        .where(
            Lote.estado == "merma",
            Lote.merma_en.is_not(None),
            Camara.restaurante_id == restaurante_id,
        )
    ).all()

    return {
        "pct_tiempo_en_rango_24h": pct_en_rango(lecturas_en_rango, total_lecturas),
        "alertas_activas": alertas_activas or 0,
        "tiempo_respuesta_promedio_min": promedio_respuesta_min(atendidas),
        "valor_en_riesgo_mxn": valor_en_riesgo(costos_en_riesgo),
        "merma_hoy_mxn": merma_en_periodo(mermas, ahora, "dia"),
        "merma_mes_mxn": merma_en_periodo(mermas, ahora, "mes"),
    }
