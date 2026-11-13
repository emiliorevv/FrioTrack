"""Pruebas de alertas, KPIs y alertas de seguridad sin base real ni red."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.config import limpiar_cache_settings
from app.db.models import Alerta, AlertaSeguridad, Usuario
from app.db.session import get_db
from app.erp.kpis import merma_en_periodo, pct_en_rango, promedio_respuesta_min, valor_en_riesgo
from app.main import create_app
from app.services import kpis as kpis_servicio

AHORA = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    """Aísla cada prueba de la configuración cacheada y del .env local."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


class ResultadoFalso:
    """Resultado mínimo de SQLAlchemy: solo lo que usan los endpoints."""

    def __init__(self, filas: list[object]) -> None:
        self._filas = filas

    def all(self) -> list[object]:
        return list(self._filas)

    def one(self) -> object:
        return self._filas[0]


class SesionFalsa:
    """Sesión falsa: entrega resultados en orden y registra consultas y commits."""

    def __init__(
        self,
        *,
        ejecutar: list[list[object]] | None = None,
        escalares: list[list[object]] | None = None,
        unicos: list[object] | None = None,
        obtener: list[object] | None = None,
    ) -> None:
        self._ejecutar = list(ejecutar or [])
        self._escalares = list(escalares or [])
        self._unicos = list(unicos or [])
        self._obtener = list(obtener or [])
        self.sentencias: list[object] = []
        self.commits = 0

    def execute(self, sentencia: object) -> ResultadoFalso:
        self.sentencias.append(sentencia)
        return ResultadoFalso(self._ejecutar.pop(0))

    def scalars(self, sentencia: object) -> ResultadoFalso:
        self.sentencias.append(sentencia)
        return ResultadoFalso(self._escalares.pop(0))

    def scalar(self, sentencia: object) -> object:
        self.sentencias.append(sentencia)
        return self._unicos.pop(0)

    def get(self, modelo: object, ident: int) -> object:
        self.sentencias.append((modelo, ident))
        return self._obtener.pop(0)

    def commit(self) -> None:
        self.commits += 1


def _cliente(sesion: SesionFalsa) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    return TestClient(app)


def _alerta(**cambios: object) -> Alerta:
    datos: dict[str, object] = {
        "id": 31,
        "camara_id": 1,
        "tipo": "temperatura",
        "abierta_en": datetime(2026, 11, 12, 18, 5, tzinfo=UTC),
        "cerrada_en": None,
        "temperatura_max_c": Decimal("3.4"),
        "atendida_por": None,
        "atendida_en": None,
        "nota": None,
        "sms_enviados": 1,
    }
    datos.update(cambios)
    return Alerta(**datos)


# --- GET /api/alertas -------------------------------------------------------


def test_get_alertas_sin_filtro_ordena_y_aplica_limite_por_defecto():
    cerrada = _alerta(
        id=30,
        camara_id=2,
        tipo="puerta",
        abierta_en=datetime(2026, 11, 12, 17, 0, tzinfo=UTC),
        cerrada_en=datetime(2026, 11, 12, 17, 30, tzinfo=UTC),
        temperatura_max_c=None,
        sms_enviados=2,
    )
    sesion = SesionFalsa(escalares=[[_alerta(), cerrada]])

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/alertas")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert [fila["id"] for fila in cuerpo] == [31, 30]
    assert cuerpo[0] == {
        "id": 31,
        "camara_id": 1,
        "tipo": "temperatura",
        "abierta_en": "2026-11-12T18:05:00+00:00",
        "cerrada_en": None,
        "atendida_por": None,
        "temperatura_max_c": 3.4,
        "sms_enviados": 1,
    }
    assert cuerpo[1]["cerrada_en"] == "2026-11-12T17:30:00+00:00"
    assert cuerpo[1]["temperatura_max_c"] is None

    consulta = str(sesion.sentencias[0])
    assert "ORDER BY alertas.abierta_en DESC" in consulta
    assert "cerrada_en IS NULL" not in consulta
    # Sin `limite` explícito se aplica el default de 50.
    assert sesion.sentencias[0].compile(compile_kwargs={"literal_binds": True}).string.endswith(
        "LIMIT 50"
    )


def test_get_alertas_activas_solo_pide_las_abiertas():
    sesion = SesionFalsa(escalares=[[_alerta()]])

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/alertas", params={"activas": "true"})

    assert respuesta.status_code == 200
    assert "cerrada_en IS NULL" in str(sesion.sentencias[0])


def test_get_alertas_respeta_el_limite_pedido():
    sesion = SesionFalsa(escalares=[[_alerta()]])

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/alertas", params={"limite": 5})

    assert respuesta.status_code == 200
    sentencia = sesion.sentencias[0]
    assert sentencia.compile(compile_kwargs={"literal_binds": True}).string.endswith("LIMIT 5")


@pytest.mark.parametrize("limite", [0, 201])
def test_get_alertas_rechaza_limite_fuera_de_rango(limite):
    sesion = SesionFalsa(escalares=[[]])

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/alertas", params={"limite": limite})

    assert respuesta.status_code == 422
    assert sesion.sentencias == []


# --- POST /api/alertas/{id}/atender ----------------------------------------


def test_atender_alerta_marca_usuario_y_fecha_sin_cerrarla():
    alerta = _alerta()
    jefe = Usuario(id=1, usuario="jefe", password_hash="hash", rol="jefe_cocina")
    sesion = SesionFalsa(obtener=[alerta], unicos=[jefe])

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/alertas/31/atender", json={"nota": "Se cerró la puerta"}
        )

    assert respuesta.status_code == 200
    assert alerta.atendida_por == 1
    assert alerta.atendida_en is not None
    assert alerta.nota == "Se cerró la puerta"
    assert alerta.cerrada_en is None
    assert sesion.commits == 1
    cuerpo = respuesta.json()
    assert cuerpo["atendida_por"] == 1
    assert cuerpo["cerrada_en"] is None


def test_atender_alerta_sin_nota_la_deja_intacta():
    alerta = _alerta()
    sesion = SesionFalsa(
        obtener=[alerta],
        unicos=[Usuario(id=1, usuario="jefe", password_hash="hash", rol="jefe_cocina")],
    )

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/alertas/31/atender", json={})

    assert respuesta.status_code == 200
    assert alerta.nota is None


def test_atender_alerta_ya_atendida_conserva_la_fecha_y_actualiza_la_nota():
    atendida_en = datetime(2026, 11, 12, 18, 10, tzinfo=UTC)
    alerta = _alerta(
        atendida_por=1,
        atendida_en=atendida_en,
        nota="Primera nota",
    )
    # Sin `unicos`: un segundo atender no debe volver a buscar al jefe.
    sesion = SesionFalsa(obtener=[alerta])

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/alertas/31/atender", json={"nota": "Nota corregida"}
        )

    assert respuesta.status_code == 200
    assert alerta.atendida_en == atendida_en
    assert alerta.atendida_por == 1
    assert alerta.nota == "Nota corregida"
    assert sesion.commits == 1
    assert sesion.sentencias == [(Alerta, 31)]


def test_atender_alerta_inexistente_regresa_404():
    sesion = SesionFalsa(obtener=[None])

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/alertas/99/atender", json={})

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Alerta no encontrada"
    assert sesion.commits == 0


def test_atender_alerta_cerrada_regresa_409():
    alerta = _alerta(cerrada_en=datetime(2026, 11, 12, 18, 30, tzinfo=UTC))
    sesion = SesionFalsa(obtener=[alerta])

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/alertas/31/atender", json={})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "La alerta ya está cerrada"
    assert sesion.commits == 0


def test_atender_alerta_sin_usuario_jefe_regresa_500_con_mensaje_claro():
    sesion = SesionFalsa(obtener=[_alerta()], unicos=[None])

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/alertas/31/atender", json={})

    assert respuesta.status_code == 500
    assert "jefe_cocina" in respuesta.json()["detail"]
    assert sesion.commits == 0


# --- GET /api/kpis ----------------------------------------------------------


def test_kpis_con_datos_calculan_todo(monkeypatch):
    monkeypatch.setattr(kpis_servicio, "_ahora", lambda: AHORA)

    # (total de lecturas en 24 h, lecturas dentro de rango) — ya contados en SQL.
    conteo_lecturas = [(3, 2)]
    atendidas = [
        (AHORA - timedelta(minutes=20), AHORA - timedelta(minutes=15)),
        (AHORA - timedelta(minutes=30), AHORA - timedelta(minutes=20)),
    ]
    costos_en_riesgo = [Decimal("1000.00"), Decimal("250.50")]
    mermas = [
        (datetime(2026, 11, 12, 16, 0, tzinfo=UTC), Decimal("100.00")),
        (datetime(2026, 11, 5, 16, 0, tzinfo=UTC), Decimal("50.00")),
        (datetime(2026, 10, 31, 18, 0, tzinfo=UTC), Decimal("25.00")),
        (datetime(2026, 11, 12, 17, 0), Decimal("20.00")),
    ]
    sesion = SesionFalsa(ejecutar=[conteo_lecturas, atendidas, mermas],
                         escalares=[costos_en_riesgo], unicos=[2])

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/kpis")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "pct_tiempo_en_rango_24h": 66.7,
        "alertas_activas": 2,
        "tiempo_respuesta_promedio_min": 7.5,
        "valor_en_riesgo_mxn": 1250.5,
        "merma_hoy_mxn": 120.0,
        "merma_mes_mxn": 170.0,
    }
    consulta_lecturas = str(sesion.sentencias[0])
    assert "lecturas.recibida_en >=" in consulta_lecturas
    assert "FILTER (WHERE" in consulta_lecturas


def test_consulta_pct_en_rango_compila_para_postgres():
    consulta = kpis_servicio._consulta_pct_en_rango(AHORA - timedelta(hours=24))
    sql = str(consulta.compile(dialect=postgresql.dialect()))

    assert "count(*)" in sql
    assert "FILTER (WHERE" in sql
    assert "BETWEEN camaras.rango_min_c AND camaras.rango_max_c" in sql
    assert "JOIN camaras ON camaras.id = lecturas.camara_id" in sql


def test_kpis_sin_datos_regresan_ceros(monkeypatch):
    monkeypatch.setattr(kpis_servicio, "_ahora", lambda: AHORA)
    sesion = SesionFalsa(ejecutar=[[(0, 0)], [], []], escalares=[[]], unicos=[0])

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/kpis")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "pct_tiempo_en_rango_24h": 0.0,
        "alertas_activas": 0,
        "tiempo_respuesta_promedio_min": 0.0,
        "valor_en_riesgo_mxn": 0.0,
        "merma_hoy_mxn": 0.0,
        "merma_mes_mxn": 0.0,
    }


# --- GET /api/seguridad/alertas --------------------------------------------


def test_seguridad_alertas_regresa_ultimas_veinte():
    filas = [
        AlertaSeguridad(
            id=7,
            regla_id="sigma-001",
            regla="Fuerza bruta",
            severidad="high",
            ts=datetime(2026, 11, 12, 18, 0, tzinfo=UTC),
            ip_origen="187.190.12.4",
            detalle={"intentos": 12},
            accion="bloquear_ip",
        ),
        AlertaSeguridad(
            id=6,
            regla_id="sigma-002",
            regla="Token revocado",
            severidad="medium",
            ts=datetime(2026, 11, 12, 17, 0, tzinfo=UTC),
            ip_origen=None,
            detalle={"sensor_id": "S-PES-01"},
            accion="revocar_token",
        ),
    ]
    sesion = SesionFalsa(escalares=[filas])

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/seguridad/alertas")

    assert respuesta.status_code == 200
    assert [fila["id"] for fila in respuesta.json()] == [7, 6]
    assert respuesta.json()[0] == {
        "id": 7,
        "regla_id": "sigma-001",
        "regla": "Fuerza bruta",
        "severidad": "high",
        "ts": "2026-11-12T18:00:00+00:00",
        "ip_origen": "187.190.12.4",
        "detalle": {"intentos": 12},
        "accion": "bloquear_ip",
    }
    consulta = str(sesion.sentencias[0])
    assert "ORDER BY alertas_seguridad.ts DESC" in consulta
    assert "LIMIT" in consulta.upper()


# --- Funciones puras de KPIs ------------------------------------------------


def test_pct_en_rango_calcula_y_redondea():
    assert pct_en_rango(2, 3) == 66.7
    assert pct_en_rango(3, 3) == 100.0
    assert pct_en_rango(0, 4) == 0.0
    assert pct_en_rango(0, 0) == 0.0


def test_promedio_respuesta_min_promedia_y_redondea():
    pares = [
        (datetime(2026, 11, 12, 10, 0, tzinfo=UTC), datetime(2026, 11, 12, 10, 5, tzinfo=UTC)),
        (datetime(2026, 11, 12, 11, 0, tzinfo=UTC), datetime(2026, 11, 12, 11, 10, tzinfo=UTC)),
    ]

    assert promedio_respuesta_min(pares) == 7.5
    assert promedio_respuesta_min(
        [(datetime(2026, 11, 12, 10, 0), datetime(2026, 11, 12, 10, 1, 30))]
    ) == 1.5
    assert promedio_respuesta_min([]) == 0.0


def test_merma_del_dia_usa_hora_de_ciudad_de_mexico():
    ahora = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)  # 12:00 en México
    mermas = [
        (datetime(2026, 11, 12, 5, 0, tzinfo=UTC), Decimal("40.00")),  # 23:00 del día 11
        (datetime(2026, 11, 12, 7, 0, tzinfo=UTC), Decimal("20.00")),  # 01:00 del día 12
        (datetime(2026, 11, 12, 17, 0), Decimal("10.00")),  # naive = UTC, 11:00 local
    ]

    assert merma_en_periodo(mermas, ahora, "dia") == 30.0


def test_merma_del_mes_respeta_el_cambio_de_mes_local():
    ahora = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)  # 12:00 del 15 de noviembre
    mermas = [
        (datetime(2026, 11, 1, 5, 0, tzinfo=UTC), Decimal("40.00")),  # 31 de octubre, 23:00
        (datetime(2026, 11, 5, 18, 0, tzinfo=UTC), Decimal("50.00")),  # 5 de noviembre
        (datetime(2026, 10, 31, 18, 0, tzinfo=UTC), Decimal("25.00")),  # octubre
    ]

    assert merma_en_periodo(mermas, ahora, "mes") == 50.0


def test_merma_en_periodo_rechaza_otro_periodo():
    with pytest.raises(ValueError, match="Periodo no soportado"):
        merma_en_periodo([], AHORA, "semana")  # type: ignore[arg-type]


def test_valor_en_riesgo_suma_decimales_sin_error_de_float():
    assert valor_en_riesgo([Decimal("1000.00"), Decimal("250.50")]) == 1250.5
    assert valor_en_riesgo([0.1, 0.2]) == 0.3
    assert valor_en_riesgo([]) == 0.0
