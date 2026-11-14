"""Pruebas del canal simulado de notificaciones; sin base ni red."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import limpiar_cache_settings
from app.db.models import Alerta, Camara, Lote
from app.services import notificaciones
from app.services.notificaciones import Notificacion

AHORA = datetime(2026, 11, 18, 19, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _url_de_dashboard(monkeypatch):
    """Fija la URL del contrato y refresca la configuración cacheada."""
    monkeypatch.setenv("DASHBOARD_URL", "http://localhost:5173")
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


class NotificadorFalso:
    """Guarda las notificaciones en vez de publicarlas."""

    def __init__(self) -> None:
        self.enviadas: list[Notificacion] = []

    def enviar(self, notificacion: Notificacion) -> None:
        self.enviadas.append(notificacion)


@pytest.fixture
def notificador_falso(monkeypatch) -> NotificadorFalso:
    falso = NotificadorFalso()
    monkeypatch.setattr(notificaciones, "notificador", falso)
    return falso


def _camara(**cambios: object) -> Camara:
    base = {
        "id": 1,
        "nombre": "Pescados y mariscos",
        "rango_min_c": Decimal("0.0"),
        "rango_max_c": Decimal("2.0"),
        "min_para_riesgo": 10,
        "min_para_merma": 60,
        "estado": "critica",
    }
    base.update(cambios)
    return Camara(**base)


def _alerta(tipo: str, temperatura_max_c: Decimal | None = None) -> Alerta:
    return Alerta(
        id=900,
        camara_id=1,
        tipo=tipo,
        abierta_en=AHORA,
        temperatura_max_c=temperatura_max_c,
        sms_enviados=0,
    )


def _lote(costo: str, estado: str = "en_riesgo", lote_id: int = 1) -> Lote:
    return Lote(
        id=lote_id,
        producto="Robalo fresco",
        camara_id=1,
        cantidad=Decimal("12.00"),
        unidad="kg",
        costo_total_mxn=Decimal(costo),
        estado=estado,
    )


# --- Mensajes ---------------------------------------------------------------


def test_alerta_de_temperatura_usa_minutos_escalados_y_el_monto_en_riesgo(
    notificador_falso,
):
    camara = _camara(fuera_de_rango_desde=AHORA - timedelta(seconds=20))
    lotes = [
        _lote("3240.00", lote_id=1),
        _lote("1610.00", lote_id=2),
        _lote("999.00", estado="ok", lote_id=3),
        _lote("500.00", estado="merma", lote_id=4),
    ]

    notificaciones.notificar_cambios(
        camara, [_alerta("temperatura", Decimal("3.4"))], lotes, [], AHORA, 30, 3.9
    )

    assert len(notificador_falso.enviadas) == 1
    enviada = notificador_falso.enviadas[0]
    assert enviada.tipo == "alerta_temperatura"
    assert enviada.camara_id == 1
    assert enviada.canal == "simulado"
    assert enviada.ts == AHORA
    assert enviada.url == "http://localhost:5173"
    assert enviada.mensaje == (
        "FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min. "
        "$4,850 en riesgo."
    )


def test_alerta_de_temperatura_sin_maximo_usa_la_lectura_actual(notificador_falso):
    camara = _camara(fuera_de_rango_desde=AHORA - timedelta(seconds=20))

    notificaciones.notificar_cambios(
        camara, [_alerta("temperatura")], [_lote("3240.00")], [], AHORA, 30, 3.9
    )

    assert notificador_falso.enviadas[0].mensaje == (
        "FríoTrack: Cámara Pescados y mariscos a 3.9 °C hace 10 min. "
        "$3,240 en riesgo."
    )


def test_alerta_de_puerta(notificador_falso):
    camara = _camara(puerta_abierta_desde=AHORA - timedelta(seconds=6))

    notificaciones.notificar_cambios(
        camara, [_alerta("puerta")], [_lote("3240.00")], [], AHORA, 30, 1.5
    )

    enviada = notificador_falso.enviadas[0]
    assert enviada.tipo == "alerta_puerta"
    assert enviada.mensaje == (
        "FríoTrack: Puerta abierta en Cámara Pescados y mariscos hace 3 min. "
        "$3,240 en riesgo."
    )


@pytest.mark.parametrize(
    ("lotes", "esperado"),
    [
        (
            [_lote("3240.00")],
            "FríoTrack: Cámara Pescados y mariscos: 1 lote pasó a merma ($3,240).",
        ),
        (
            [_lote("3240.00", lote_id=1), _lote("1610.00", lote_id=2)],
            "FríoTrack: Cámara Pescados y mariscos: 2 lotes pasaron a merma ($4,850).",
        ),
    ],
    ids=["singular", "plural"],
)
def test_merma_respeta_singular_y_plural(notificador_falso, lotes, esperado):
    notificaciones.notificar_cambios(
        _camara(), [], [], lotes, AHORA, 30, 1.5
    )

    enviada = notificador_falso.enviadas[0]
    assert enviada.tipo == "merma"
    assert enviada.mensaje == esperado


def test_monto_cero_omite_la_clausula_de_dinero(notificador_falso):
    camara = _camara(fuera_de_rango_desde=AHORA - timedelta(seconds=20))

    notificaciones.notificar_cambios(
        camara, [_alerta("temperatura", Decimal("3.4"))], [], [], AHORA, 30, 3.9
    )

    mensaje = notificador_falso.enviadas[0].mensaje
    assert mensaje == "FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min."
    assert "$" not in mensaje
    assert "  " not in mensaje


def test_sin_cambios_no_notifica(notificador_falso):
    notificaciones.notificar_cambios(
        _camara(), [], [_lote("3240.00")], [], AHORA, 30, 1.5
    )

    assert notificador_falso.enviadas == []


# --- Notificador simulado ---------------------------------------------------


def test_notificador_simulado_publica_el_evento_del_contrato(monkeypatch):
    publicados: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        notificaciones.bus, "publicar", lambda evento, data: publicados.append((evento, data))
    )
    notificacion = Notificacion(
        tipo="alerta_temperatura",
        camara_id=1,
        mensaje=(
            "FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min. "
            "$4,850 en riesgo."
        ),
        ts=datetime(2026, 11, 18, 19, 5, tzinfo=UTC),
        url="http://localhost:5173",
    )

    notificaciones.NotificadorSimulado().enviar(notificacion)

    assert publicados == [
        (
            "notificacion",
            {
                "canal": "simulado",
                "tipo": "alerta_temperatura",
                "camara_id": 1,
                "mensaje": (
                    "FríoTrack: Cámara Pescados y mariscos a 3.4 °C hace 10 min. "
                    "$4,850 en riesgo."
                ),
                "ts": "2026-11-18T19:05:00+00:00",
                "url": "http://localhost:5173",
            },
        )
    ]


def test_sin_timestamp_reporta_un_minuto(notificador_falso):
    notificaciones.notificar_cambios(
        _camara(), [_alerta("puerta")], [], [], AHORA, 30, 1.5
    )

    assert "hace 1 min." in notificador_falso.enviadas[0].mensaje


# --- Robustez ---------------------------------------------------------------


def test_un_fallo_del_notificador_no_se_propaga(monkeypatch):
    class NotificadorRoto:
        def enviar(self, _notificacion: Notificacion) -> None:
            raise RuntimeError("canal caído")

    monkeypatch.setattr(notificaciones, "notificador", NotificadorRoto())
    camara = _camara(fuera_de_rango_desde=AHORA - timedelta(seconds=20))

    # No debe lanzar: la ingesta ya quedó confirmada antes de notificar.
    notificaciones.notificar_cambios(
        camara,
        [_alerta("temperatura", Decimal("3.4"))],
        [_lote("3240.00")],
        [_lote("3240.00", estado="merma", lote_id=2)],
        AHORA,
        30,
        3.9,
    )
