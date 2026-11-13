"""Evaluación pura de una lectura contra las reglas del ERP.

No importa SQLAlchemy ni toca la base: recibe objetos con los atributos que
necesita (los modelos ORM o fakes de prueba) y regresa qué transiciones aplicar.
El servicio de telemetría es quien persiste el resultado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.erp.reglas import (
    debe_abrir_alerta_puerta,
    debe_abrir_alerta_temperatura,
    debe_marcar_merma,
    esta_en_rango,
)

TIPO_ALERTA_TEMPERATURA = "temperatura"
TIPO_ALERTA_PUERTA = "puerta"


class CamaraEvaluable(Protocol):
    """Lo mínimo que necesita la evaluación de una cámara."""

    rango_min_c: float | Decimal
    rango_max_c: float | Decimal
    min_para_riesgo: int
    min_para_merma: int
    fuera_de_rango_desde: datetime | None
    puerta_abierta_desde: datetime | None


class LoteEvaluable(Protocol):
    """Lo mínimo que necesita la evaluación de un lote."""

    estado: str


class AlertaEvaluable(Protocol):
    """Lo mínimo que necesita la evaluación de una alerta abierta."""

    tipo: str
    temperatura_max_c: float | Decimal | None


@dataclass
class ResultadoEvaluacion:
    """Transiciones que el servicio debe aplicar a los objetos persistidos."""

    abrir_alerta_temperatura: bool = False
    cerrar_alerta_temperatura: bool = False
    abrir_alerta_puerta: bool = False
    cerrar_alerta_puerta: bool = False
    lotes_a_riesgo: list[LoteEvaluable] = field(default_factory=list)
    lotes_a_merma: list[LoteEvaluable] = field(default_factory=list)
    lotes_a_recuperar: list[LoteEvaluable] = field(default_factory=list)
    temperatura_max_c: Decimal | None = None


def _como_decimal(valor: float | Decimal) -> Decimal:
    """Normaliza a Decimal para poder comparar y guardar `temperatura_max_c`."""
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _maximo(actual: float | Decimal | None, temperatura: Decimal) -> Decimal:
    """Máximo entre la peor lectura de la alerta y la lectura actual."""
    if actual is None:
        return temperatura
    return max(_como_decimal(actual), temperatura)


def _alerta_de_tipo(
    alertas_abiertas: Sequence[AlertaEvaluable], tipo: str
) -> AlertaEvaluable | None:
    """Regresa la alerta abierta del tipo pedido, si existe."""
    return next((alerta for alerta in alertas_abiertas if alerta.tipo == tipo), None)


def evaluar_lectura(
    camara: CamaraEvaluable,
    temperatura_c: float,
    puerta_abierta: bool,
    ahora: datetime,
    escala: float,
    lotes: Sequence[LoteEvaluable],
    alertas_abiertas: Sequence[AlertaEvaluable],
) -> ResultadoEvaluacion:
    """Evalúa una lectura y calcula las transiciones de alertas y lotes.

    `camara.fuera_de_rango_desde` y `camara.puerta_abierta_desde` ya deben venir
    actualizados por el servicio con la lectura actual.
    """
    resultado = ResultadoEvaluacion()
    en_rango = esta_en_rango(
        temperatura_c, float(camara.rango_min_c), float(camara.rango_max_c)
    )
    alerta_temperatura = _alerta_de_tipo(alertas_abiertas, TIPO_ALERTA_TEMPERATURA)
    alerta_puerta = _alerta_de_tipo(alertas_abiertas, TIPO_ALERTA_PUERTA)

    if en_rango:
        # Volver al rango cierra la alerta y recupera lo que solo estaba en riesgo;
        # la merma ya registrada no se revierte.
        if alerta_temperatura is not None:
            resultado.cerrar_alerta_temperatura = True
        resultado.lotes_a_recuperar = [
            lote for lote in lotes if lote.estado == "en_riesgo"
        ]
    else:
        if alerta_temperatura is None:
            if debe_abrir_alerta_temperatura(
                camara.fuera_de_rango_desde, ahora, camara.min_para_riesgo, escala
            ):
                resultado.abrir_alerta_temperatura = True
                resultado.temperatura_max_c = _como_decimal(temperatura_c)
        else:
            resultado.temperatura_max_c = _maximo(
                alerta_temperatura.temperatura_max_c, _como_decimal(temperatura_c)
            )

        if debe_marcar_merma(
            camara.fuera_de_rango_desde, ahora, camara.min_para_merma, escala
        ):
            resultado.lotes_a_merma = [lote for lote in lotes if lote.estado != "merma"]
        elif debe_abrir_alerta_temperatura(
            camara.fuera_de_rango_desde, ahora, camara.min_para_riesgo, escala
        ):
            resultado.lotes_a_riesgo = [lote for lote in lotes if lote.estado == "ok"]

    if puerta_abierta:
        if alerta_puerta is None and debe_abrir_alerta_puerta(
            camara.puerta_abierta_desde, ahora, escala
        ):
            resultado.abrir_alerta_puerta = True
    elif alerta_puerta is not None:
        resultado.cerrar_alerta_puerta = True

    return resultado
