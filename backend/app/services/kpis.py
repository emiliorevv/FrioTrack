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


def _consulta_pct_en_rango(desde: datetime) -> Select[tuple[int, int]]:
    """Cuenta lecturas totales y lecturas dentro de rango desde `desde`, en SQL.

    `count(*) FILTER (...)` compila en Postgres y evita traer las lecturas a
    Python; los extremos cuentan como dentro de rango, igual que antes.
    """
    dentro = func.count().filter(
        Lectura.temperatura_c.between(Camara.rango_min_c, Camara.rango_max_c)
    )
    return (
        select(func.count(), dentro)
        .select_from(Lectura)
        .join(Camara, Camara.id == Lectura.camara_id)
        .where(Lectura.recibida_en >= desde)
    )


def calcular_kpis(db: Session) -> dict[str, Any]:
    """Calcula los seis KPIs del encabezado con las queries actuales."""
    ahora = _ahora()
    desde = ahora - timedelta(hours=24)

    total_lecturas, lecturas_en_rango = db.execute(_consulta_pct_en_rango(desde)).one()

    alertas_activas = db.scalar(
        select(func.count()).select_from(Alerta).where(Alerta.cerrada_en.is_(None))
    )

    atendidas = db.execute(
        select(Alerta.abierta_en, Alerta.atendida_en).where(Alerta.atendida_en.is_not(None))
    ).all()

    costos_en_riesgo = db.scalars(
        select(Lote.costo_total_mxn).where(Lote.estado == "en_riesgo")
    ).all()

    mermas = db.execute(
        select(Lote.merma_en, Lote.costo_total_mxn).where(
            Lote.estado == "merma", Lote.merma_en.is_not(None)
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
