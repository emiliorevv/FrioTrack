"""Endpoints de consulta: cámaras, lecturas y lotes.

Auth pendiente (fase posterior): el contrato pide el JWT de usuario del dashboard
para estas rutas; mientras no exista el login, quedan abiertas en local.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Camara, Lectura, Lote
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["consulta"])

VENTANA_POR_DEFECTO = timedelta(hours=2)
LIMITE_LECTURAS = 5000

Db = Annotated[Session, Depends(get_db)]


def _flotante(valor: Decimal | None) -> float | None:
    """Convierte numeric de Postgres a float para que el JSON sea numérico."""
    return None if valor is None else float(valor)


def _ultima_lectura(db: Session, camara: Camara) -> Lectura | None:
    """Usa el atajo de la cámara y, si falta, busca por recibida_en."""
    lectura = None
    if camara.ultima_lectura_id is not None:
        lectura = db.get(Lectura, camara.ultima_lectura_id)
    if lectura is None:
        lectura = (
            db.execute(
                select(Lectura)
                .where(Lectura.camara_id == camara.id)
                .order_by(Lectura.recibida_en.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
    return lectura


def _resumen_lectura(lectura: Lectura | None) -> dict[str, Any] | None:
    """Arma el objeto `ultima_lectura` del contrato (o null si no hay)."""
    if lectura is None:
        return None
    return {
        "ts": lectura.ts.isoformat(),
        "temperatura_c": _flotante(lectura.temperatura_c),
        "humedad_pct": _flotante(lectura.humedad_pct),
        "puerta_abierta": lectura.puerta_abierta,
    }


@router.get("/camaras")
def listar_camaras(db: Db) -> list[dict[str, Any]]:
    """Lista las cámaras con su última lectura y el valor de sus lotes en riesgo."""
    camaras = db.execute(select(Camara).order_by(Camara.id)).scalars().all()
    riesgo = {
        camara_id: float(total or 0)
        for camara_id, total in db.execute(
            select(Lote.camara_id, func.sum(Lote.costo_total_mxn))
            .where(Lote.estado == "en_riesgo")
            .group_by(Lote.camara_id)
        ).all()
    }

    return [
        {
            "id": camara.id,
            "nombre": camara.nombre,
            "rango_min_c": _flotante(camara.rango_min_c),
            "rango_max_c": _flotante(camara.rango_max_c),
            "min_para_riesgo": camara.min_para_riesgo,
            "min_para_merma": camara.min_para_merma,
            "estado": camara.estado,
            "ultima_lectura": _resumen_lectura(_ultima_lectura(db, camara)),
            "valor_en_riesgo_mxn": riesgo.get(camara.id, 0.0),
        }
        for camara in camaras
    ]


@router.get("/camaras/{id}/lecturas")
def listar_lecturas(
    id: int,
    db: Db,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> list[dict[str, Any]]:
    """Lecturas de una cámara; sin rango, las últimas 2 horas por `recibida_en`."""
    if db.get(Camara, id) is None:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")

    if hasta is None:
        hasta = datetime.now(UTC)
    if desde is None:
        desde = hasta - VENTANA_POR_DEFECTO

    lecturas = (
        db.execute(
            select(Lectura)
            .where(
                Lectura.camara_id == id,
                Lectura.recibida_en >= desde,
                Lectura.recibida_en <= hasta,
            )
            .order_by(Lectura.recibida_en)
            .limit(LIMITE_LECTURAS)
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": lectura.id,
            "ts": lectura.ts.isoformat(),
            "recibida_en": lectura.recibida_en.isoformat(),
            "temperatura_c": _flotante(lectura.temperatura_c),
            "humedad_pct": _flotante(lectura.humedad_pct),
            "puerta_abierta": lectura.puerta_abierta,
            "sospechosa": lectura.sospechosa,
        }
        for lectura in lecturas
    ]


@router.get("/lotes")
def listar_lotes(
    db: Db,
    camara_id: int | None = None,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    """Lotes de inventario, opcionalmente filtrados por cámara y estado."""
    if camara_id is not None and db.get(Camara, camara_id) is None:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")

    consulta = select(Lote)
    if camara_id is not None:
        consulta = consulta.where(Lote.camara_id == camara_id)
    if estado is not None:
        consulta = consulta.where(Lote.estado == estado)
    lotes = db.execute(consulta.order_by(Lote.id)).scalars().all()

    return [
        {
            "id": lote.id,
            "producto": lote.producto,
            "camara_id": lote.camara_id,
            "cantidad": _flotante(lote.cantidad),
            "unidad": lote.unidad,
            "costo_total_mxn": _flotante(lote.costo_total_mxn),
            "caducidad": lote.caducidad.isoformat(),
            "estado": lote.estado,
        }
        for lote in lotes
    ]
