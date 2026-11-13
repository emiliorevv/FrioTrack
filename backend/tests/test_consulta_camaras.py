"""Pruebas de los endpoints de consulta con una sesión falsa (sin base ni red)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.db.models import Camara, Lectura, Lote
from app.db.session import get_db
from app.main import create_app
from app.routers.camaras import LIMITE_LECTURAS


class _Resultado:
    """Imita lo mínimo de un Result de SQLAlchemy."""

    def __init__(self, filas: list[Any]):
        self._filas = filas

    def scalars(self) -> _Resultado:
        return self

    def all(self) -> list[Any]:
        return list(self._filas)

    def first(self) -> Any | None:
        return self._filas[0] if self._filas else None


class SesionFalsa:
    """Sesión en memoria que filtra y ordena los datos prefabricados.

    Reconoce las consultas del router por la tabla del SELECT y por los parámetros
    ligados, sin conectarse a ninguna base.
    """

    def __init__(
        self,
        camaras: list[Camara] | None = None,
        lecturas: list[Lectura] | None = None,
        lotes: list[Lote] | None = None,
    ):
        self.camaras = camaras or []
        self.lecturas = lecturas or []
        self.lotes = lotes or []
        # Sentencias recibidas, para inspeccionar el SQL que arma el router.
        self.consultas: list[Any] = []

    def get(self, modelo: type, ident: int) -> Any | None:
        filas = {
            Camara: self.camaras,
            Lectura: self.lecturas,
            Lote: self.lotes,
        }[modelo]
        return next((fila for fila in filas if fila.id == ident), None)

    def execute(self, stmt: Any) -> _Resultado:
        sql = str(stmt).lower()
        params = stmt.compile().params
        self.consultas.append(stmt)

        if "group by" in sql:
            return _Resultado(self._sumas_en_riesgo(params))
        if "from lotes" in sql:
            return _Resultado(self._lotes(params))
        if "from lecturas" in sql:
            # `_limit` es privado en SQLAlchemy, pero aquí alcanza para imitar el LIMIT.
            limite = getattr(stmt, "_limit", None)
            return _Resultado(self._lecturas(sql, params, limite))
        if "from camaras" in sql:
            return _Resultado(sorted(self.camaras, key=lambda camara: camara.id))
        raise AssertionError(f"Consulta no soportada por la sesión falsa:\n{stmt}")

    def _sumas_en_riesgo(self, params: dict[str, Any]) -> list[tuple[int, Decimal]]:
        estado = params.get("estado_1", "en_riesgo")
        totales: dict[int, Decimal] = {}
        for lote in self.lotes:
            if lote.estado == estado:
                totales[lote.camara_id] = totales.get(lote.camara_id, Decimal(0)) + (
                    lote.costo_total_mxn
                )
        return list(totales.items())

    def _lotes(self, params: dict[str, Any]) -> list[Lote]:
        filas = list(self.lotes)
        if "camara_id_1" in params:
            filas = [lote for lote in filas if lote.camara_id == params["camara_id_1"]]
        if "estado_1" in params:
            filas = [lote for lote in filas if lote.estado == params["estado_1"]]
        return sorted(filas, key=lambda lote: lote.id)

    def _lecturas(
        self,
        sql: str,
        params: dict[str, Any],
        limite: int | None = None,
    ) -> list[Lectura]:
        filas = list(self.lecturas)
        if "camara_id_1" in params:
            filas = [lectura for lectura in filas if lectura.camara_id == params["camara_id_1"]]
        if "id_1" in params:
            filas = [lectura for lectura in filas if lectura.id == params["id_1"]]

        cotas = sorted(valor for clave, valor in params.items() if clave.startswith("recibida_en_"))
        if cotas:
            filas = [lectura for lectura in filas if lectura.recibida_en >= cotas[0]]
        if len(cotas) > 1:
            filas = [lectura for lectura in filas if lectura.recibida_en <= cotas[-1]]

        descendente = " desc" in sql
        filas = sorted(filas, key=lambda lectura: lectura.recibida_en, reverse=descendente)
        return filas[:limite] if limite is not None else filas


@pytest.fixture(autouse=True)
def _entorno_local(monkeypatch):
    """Arma la app sin validaciones de producción y sin caché de settings."""
    monkeypatch.setenv("ENTORNO", "local")
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def _cliente(sesion: SesionFalsa) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    return TestClient(app)


def _camara(
    id: int,
    nombre: str,
    rango_min_c: str,
    rango_max_c: str,
    min_para_riesgo: int,
    min_para_merma: int,
    estado: str,
    ultima_lectura_id: int | None,
) -> Camara:
    return Camara(
        id=id,
        nombre=nombre,
        rango_min_c=Decimal(rango_min_c),
        rango_max_c=Decimal(rango_max_c),
        min_para_riesgo=min_para_riesgo,
        min_para_merma=min_para_merma,
        estado=estado,
        ultima_lectura_id=ultima_lectura_id,
    )


def _lectura(
    id: int,
    camara_id: int,
    recibida_en: datetime,
    temperatura_c: str = "1.4",
    humedad_pct: str = "88.0",
    puerta_abierta: bool = False,
    sospechosa: bool = False,
) -> Lectura:
    return Lectura(
        id=id,
        camara_id=camara_id,
        sensor_id="S-PES-01",
        ts=recibida_en,
        recibida_en=recibida_en,
        temperatura_c=Decimal(temperatura_c),
        humedad_pct=Decimal(humedad_pct),
        puerta_abierta=puerta_abierta,
        sospechosa=sospechosa,
    )


def _lote(
    id: int,
    camara_id: int,
    producto: str,
    cantidad: str,
    costo_total_mxn: str,
    estado: str,
    caducidad: date,
) -> Lote:
    return Lote(
        id=id,
        producto=producto,
        camara_id=camara_id,
        cantidad=Decimal(cantidad),
        unidad="kg",
        costo_total_mxn=Decimal(costo_total_mxn),
        caducidad=caducidad,
        estado=estado,
    )


@pytest.fixture
def mundo() -> dict[str, Any]:
    """Cinco cámaras, lotes y lecturas relativas al momento de la prueba."""
    ahora = datetime.now(UTC)
    camaras = [
        _camara(1, "Pescados y mariscos", "0.0", "2.0", 10, 60, "alerta", 101),
        _camara(2, "Carnes y aves", "0.0", "4.0", 15, 120, "en_rango", None),
        _camara(3, "Lácteos", "1.0", "4.0", 20, 180, "en_rango", 301),
        _camara(4, "Verduras y frutas", "4.0", "8.0", 30, 240, "en_rango", 401),
        _camara(5, "Congelador", "-22.0", "-18.0", 20, 120, "en_rango", None),
    ]
    lecturas = [
        _lectura(101, 1, ahora - timedelta(minutes=5), "3.1", "85.5", True),
        _lectura(102, 1, ahora - timedelta(hours=3), "2.5", "87.0"),
        _lectura(103, 1, ahora - timedelta(minutes=90), "2.0", "86.0"),
        _lectura(201, 2, ahora - timedelta(minutes=20), "2.0", "80.0"),
        _lectura(202, 2, ahora - timedelta(minutes=2), "2.2", "81.0"),
        _lectura(301, 3, ahora - timedelta(minutes=10), "3.0", "75.0"),
        _lectura(401, 4, ahora - timedelta(minutes=1), "6.0", "70.0", sospechosa=True),
    ]
    lotes = [
        _lote(1, 1, "Robalo fresco", "12.00", "3240.00", "en_riesgo", date(2026, 11, 20)),
        _lote(2, 1, "Camarón", "5.00", "1610.00", "en_riesgo", date(2026, 11, 21)),
        _lote(3, 1, "Pulpo", "4.00", "1120.00", "ok", date(2026, 11, 20)),
        _lote(4, 2, "Arrachera", "10.00", "3100.00", "en_riesgo", date(2026, 11, 23)),
        _lote(5, 2, "Pechuga de pollo", "15.00", "1650.00", "ok", date(2026, 11, 21)),
        _lote(6, 3, "Crema", "6.00", "420.00", "ok", date(2026, 11, 25)),
        _lote(7, 4, "Lechuga", "20.00", "300.00", "en_riesgo", date(2026, 11, 22)),
        _lote(8, 5, "Helado", "8.00", "760.00", "merma", date(2026, 12, 27)),
    ]
    return {
        "sesion": SesionFalsa(camaras=camaras, lecturas=lecturas, lotes=lotes),
        "ahora": ahora,
    }


def test_camaras_devuelve_cinco_con_ultima_lectura_y_valor_en_riesgo(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/camaras")

    assert respuesta.status_code == 200
    camaras = respuesta.json()
    assert [camara["id"] for camara in camaras] == [1, 2, 3, 4, 5]
    assert camaras[0] == {
        "id": 1,
        "nombre": "Pescados y mariscos",
        "rango_min_c": 0.0,
        "rango_max_c": 2.0,
        "min_para_riesgo": 10,
        "min_para_merma": 60,
        "estado": "alerta",
        "ultima_lectura": {
            "ts": (mundo["ahora"] - timedelta(minutes=5)).isoformat(),
            "temperatura_c": 3.1,
            "humedad_pct": 85.5,
            "puerta_abierta": True,
        },
        "valor_en_riesgo_mxn": 4850.0,
    }
    # Cámara 2 no tiene ultima_lectura_id: se usa la lectura más reciente por recibida_en.
    assert camaras[1]["ultima_lectura"]["ts"] == (
        mundo["ahora"] - timedelta(minutes=2)
    ).isoformat()
    assert camaras[1]["valor_en_riesgo_mxn"] == 3100.0
    assert camaras[3]["valor_en_riesgo_mxn"] == 300.0
    assert camaras[4]["valor_en_riesgo_mxn"] == 0.0

    assert all(isinstance(camara["id"], int) for camara in camaras)
    assert all(isinstance(camara["rango_min_c"], float) for camara in camaras)
    assert all(isinstance(camara["rango_max_c"], float) for camara in camaras)
    assert all(isinstance(camara["valor_en_riesgo_mxn"], float) for camara in camaras)
    ultima = camaras[0]["ultima_lectura"]
    assert isinstance(ultima["temperatura_c"], float)
    assert isinstance(ultima["humedad_pct"], float)
    assert isinstance(ultima["puerta_abierta"], bool)


def test_camara_sin_lecturas_devuelve_ultima_lectura_null(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        camaras = cliente.get("/api/camaras").json()

    assert camaras[4]["ultima_lectura"] is None


def test_lecturas_de_camara_inexistente_devuelve_404(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/camaras/999/lecturas")

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "Cámara no encontrada"}


def test_lecturas_por_defecto_son_las_ultimas_dos_horas_en_orden_ascendente(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/camaras/1/lecturas")

    assert respuesta.status_code == 200
    lecturas = respuesta.json()
    # 102 queda fuera de la ventana de 2 h y la 101 es más reciente que la 103.
    assert [lectura["id"] for lectura in lecturas] == [103, 101]
    assert [lectura["recibida_en"] for lectura in lecturas] == sorted(
        lectura["recibida_en"] for lectura in lecturas
    )
    assert lecturas[-1] == {
        "id": 101,
        "ts": (mundo["ahora"] - timedelta(minutes=5)).isoformat(),
        "recibida_en": (mundo["ahora"] - timedelta(minutes=5)).isoformat(),
        "temperatura_c": 3.1,
        "humedad_pct": 85.5,
        "puerta_abierta": True,
        "sospechosa": False,
    }
    assert all(isinstance(lectura["temperatura_c"], float) for lectura in lecturas)
    assert all(isinstance(lectura["humedad_pct"], float) for lectura in lecturas)
    assert all(isinstance(lectura["puerta_abierta"], bool) for lectura in lecturas)
    assert all(isinstance(lectura["sospechosa"], bool) for lectura in lecturas)


def test_lecturas_respetan_desde_y_hasta(mundo):
    desde = (mundo["ahora"] - timedelta(hours=4)).isoformat()
    hasta = (mundo["ahora"] - timedelta(hours=1)).isoformat()

    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/camaras/1/lecturas", params={"desde": desde, "hasta": hasta})

    assert respuesta.status_code == 200
    assert [lectura["id"] for lectura in respuesta.json()] == [102, 103]


def test_lecturas_con_solo_desde_usa_la_ventana_hasta_ahora(mundo):
    desde = (mundo["ahora"] - timedelta(minutes=100)).isoformat()

    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/camaras/1/lecturas", params={"desde": desde})

    assert respuesta.status_code == 200
    assert [lectura["id"] for lectura in respuesta.json()] == [103, 101]


def test_lecturas_con_solo_hasta_usa_las_dos_horas_anteriores(mundo):
    hasta = (mundo["ahora"] - timedelta(hours=1)).isoformat()

    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/camaras/1/lecturas", params={"hasta": hasta})

    assert respuesta.status_code == 200
    assert [lectura["id"] for lectura in respuesta.json()] == [102, 103]


def test_lecturas_devuelve_las_mas_recientes_cuando_exceden_el_limite():
    total = LIMITE_LECTURAS + 3
    ahora = datetime.now(UTC)
    camaras = [_camara(1, "Pescados y mariscos", "0.0", "2.0", 10, 60, "alerta", None)]
    # La lectura con id más alto es la más reciente; todas caben en la ventana de 2 h.
    lecturas = [
        _lectura(id, 1, ahora - timedelta(seconds=total - id)) for id in range(1, total + 1)
    ]
    sesion = SesionFalsa(camaras=camaras, lecturas=lecturas)

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/camaras/1/lecturas")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    # Se descartan las 3 más viejas: con orden ascendente + LIMIT se perdían las recientes.
    assert [lectura["id"] for lectura in cuerpo] == list(range(4, total + 1))
    recibidas = [lectura["recibida_en"] for lectura in cuerpo]
    assert recibidas == sorted(recibidas)

    consulta = sesion.consultas[0]
    assert "order by lecturas.recibida_en desc" in str(consulta).lower()
    assert consulta._limit == LIMITE_LECTURAS


def test_lotes_sin_filtros_devuelve_todos_en_orden(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/lotes")

    assert respuesta.status_code == 200
    lotes = respuesta.json()
    assert [lote["id"] for lote in lotes] == list(range(1, 9))
    assert lotes[0] == {
        "id": 1,
        "producto": "Robalo fresco",
        "camara_id": 1,
        "cantidad": 12.0,
        "unidad": "kg",
        "costo_total_mxn": 3240.0,
        "caducidad": "2026-11-20",
        "estado": "en_riesgo",
    }
    assert all(isinstance(lote["cantidad"], float) for lote in lotes)
    assert all(isinstance(lote["costo_total_mxn"], float) for lote in lotes)
    assert all(isinstance(lote["camara_id"], int) for lote in lotes)


def test_lotes_filtra_por_camara_y_estado(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        por_camara = cliente.get("/api/lotes", params={"camara_id": 1})
        por_estado = cliente.get("/api/lotes", params={"estado": "en_riesgo"})
        ambos = cliente.get("/api/lotes", params={"camara_id": 1, "estado": "ok"})

    assert [lote["id"] for lote in por_camara.json()] == [1, 2, 3]
    assert [lote["id"] for lote in por_estado.json()] == [1, 2, 4, 7]
    assert [lote["id"] for lote in ambos.json()] == [3]


def test_lotes_de_camara_existente_sin_lotes_devuelve_lista_vacia(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/lotes", params={"camara_id": 5, "estado": "en_riesgo"})

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_lotes_de_camara_inexistente_devuelve_404(mundo):
    with _cliente(mundo["sesion"]) as cliente:
        respuesta = cliente.get("/api/lotes", params={"camara_id": 999})

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "Cámara no encontrada"}
