"""Pruebas del CRUD de cámaras y sensores con una sesión falsa en memoria.

No tocan base de datos, red ni SQLite: la sesión imita las consultas que usan
los routers y el servicio de telemetría.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.core.auth import crear_token, get_restaurante_id, sesion_si_auth
from app.db.models import Alerta, Camara, Lectura, Lote, Sensor, Usuario
from app.db.session import get_db
from app.main import create_app
from app.routers import camaras as camaras_mod

DATOS_CAMARA = {
    "nombre": "Barra fría",
    "rango_min_c": -5.0,
    "rango_max_c": 5.0,
    "min_para_riesgo": 10,
    "min_para_merma": 60,
}

def _payload(sensor_id: str, camara_id: int = 1) -> dict[str, object]:
    return {
        "sensor_id": sensor_id,
        "camara_id": camara_id,
        "ts": "2026-11-18T13:05:00-06:00",
        "temperatura_c": 1.4,
        "humedad_pct": 88,
        "puerta_abierta": False,
    }

MENSAJE_CAMARA_CON_DATOS = (
    "La cámara tiene datos asociados; desactívala o elimina primero sus sensores."
)


class Resultado:
    """Resultado mínimo de SQLAlchemy."""

    def __init__(self, filas: list[Any]) -> None:
        self._filas = list(filas)

    def scalars(self) -> Resultado:
        return self

    def all(self) -> list[Any]:
        return list(self._filas)

    def first(self) -> Any | None:
        return self._filas[0] if self._filas else None

    def one(self) -> Any:
        return self._filas[0]

    def __iter__(self):
        return iter(self._filas)


class SesionFalsa:
    """Sesión en memoria con las operaciones que usan los endpoints y la ingesta."""

    def __init__(self) -> None:
        self.camaras: dict[int, Camara] = {}
        self.sensores: dict[str, Sensor] = {}
        self.usuarios: dict[int, Usuario] = {}
        self.lecturas: list[Lectura] = []
        self.lotes: list[Lote] = []
        self.alertas: list[Alerta] = []
        self.agregados: list[object] = []
        self.eliminados: list[object] = []
        self.consultas: list[object] = []
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0
        self.refreshes: list[object] = []
        self.siguiente_camara = 1
        self.siguiente_lectura = 1000

    # --- escritura ---------------------------------------------------------

    def add(self, fila: object) -> None:
        self.agregados.append(fila)
        if isinstance(fila, Camara):
            if fila.id is None:
                fila.id = self._nuevo_id_camara()
            self.camaras[fila.id] = fila
        elif isinstance(fila, Sensor):
            self.sensores[fila.id] = fila
        elif isinstance(fila, Lectura):
            if fila.id is None:
                fila.id = self.siguiente_lectura
                self.siguiente_lectura += 1
            self.lecturas.append(fila)

    def _nuevo_id_camara(self) -> int:
        ident = self.siguiente_camara
        self.siguiente_camara += 1
        return ident

    def flush(self) -> None:
        self.flushes += 1
        for fila in self.agregados:
            if isinstance(fila, Camara) and fila.id is None:
                fila.id = self._nuevo_id_camara()
                self.camaras[fila.id] = fila
            elif isinstance(fila, Lectura) and fila.id is None:
                fila.id = self.siguiente_lectura
                self.siguiente_lectura += 1

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, fila: object) -> None:
        self.refreshes.append(fila)

    def delete(self, fila: object) -> None:
        self.eliminados.append(fila)
        if isinstance(fila, Camara):
            self.camaras.pop(fila.id, None)
        elif isinstance(fila, Sensor):
            self.sensores.pop(fila.id, None)

    # --- lectura -----------------------------------------------------------

    def get(self, modelo: object, ident: object, **_kwargs: object) -> object | None:
        if modelo is Camara:
            return self.camaras.get(ident)  # type: ignore[arg-type]
        if modelo is Sensor:
            return self.sensores.get(ident)  # type: ignore[arg-type]
        if modelo is Usuario:
            return self.usuarios.get(ident)  # type: ignore[arg-type]
        return None

    def scalar(self, sentencia: object) -> object | None:
        self.consultas.append(sentencia)
        sql = str(sentencia)
        params = sentencia.compile().params  # type: ignore[attr-defined]
        if "EXISTS" in sql.upper():
            return self._existe(sql, params)
        raise AssertionError(f"scalar no soportado:\n{sentencia}")

    def _existe(self, sql: str, params: dict[str, Any]) -> bool:
        """Evalúa el EXISTS de borrado de sensor o el combinado de cámara."""
        if "sensor_id" in sql:
            return any(
                lectura.sensor_id == params.get("sensor_id_1")
                for lectura in self.lecturas
            )
        camara_id = next(
            (valor for valor in params.values() if isinstance(valor, int)),
            None,
        )
        return (
            any(sensor.camara_id == camara_id for sensor in self.sensores.values())
            or any(lote.camara_id == camara_id for lote in self.lotes)
            or any(lectura.camara_id == camara_id for lectura in self.lecturas)
            or any(alerta.camara_id == camara_id for alerta in self.alertas)
        )

    def scalars(self, sentencia: object) -> Resultado:
        self.consultas.append(sentencia)
        sql = str(sentencia).lower()
        params = sentencia.compile().params  # type: ignore[attr-defined]
        if "from lotes" in sql:
            return Resultado(
                [lote for lote in self.lotes if lote.camara_id == params.get("camara_id_1")]
            )
        if "from alertas" in sql:
            return Resultado(
                [
                    alerta
                    for alerta in self.alertas
                    if alerta.camara_id == params.get("camara_id_1")
                    and alerta.cerrada_en is None
                    and ("tipo_1" not in params or alerta.tipo == params["tipo_1"])
                ]
            )
        if "from lecturas" in sql:
            return Resultado(self._lecturas(sentencia, sql, params))
        return Resultado([])

    def execute(self, sentencia: object) -> Resultado:
        self.consultas.append(sentencia)
        sql = str(sentencia).lower()
        params = sentencia.compile().params  # type: ignore[attr-defined]

        if "from sensores" in sql:
            tenant = params.get("restaurante_id_1")
            filas = []
            for sensor in sorted(self.sensores.values(), key=lambda fila: fila.id):
                camara = self.camaras.get(sensor.camara_id)
                if camara is not None and camara.restaurante_id == tenant:
                    filas.append((sensor, camara.nombre))
            return Resultado(filas)

        if "group by" in sql and "from lotes" in sql:
            ids = params.get("camara_id_1")
            if isinstance(ids, (list, tuple, set, frozenset)):
                lotes = [lote for lote in self.lotes if lote.camara_id in ids]
            else:
                lotes = list(self.lotes)
            return Resultado(self._sumas_por_camara(lotes))

        if "max(" in sql and "from lecturas" in sql:
            tenant = params.get("restaurante_id_1")
            ultimas: dict[str, datetime] = {}
            for lectura in self.lecturas:
                camara = self.camaras.get(lectura.camara_id)
                if camara is None or camara.restaurante_id != tenant:
                    continue
                actual = ultimas.get(lectura.sensor_id)
                if actual is None or lectura.recibida_en > actual:
                    ultimas[lectura.sensor_id] = lectura.recibida_en
            return Resultado(list(ultimas.items()))

        if "from lecturas" in sql:
            return Resultado(self._lecturas(sentencia, sql, params))

        if "from camaras" in sql:
            tenant = params.get("restaurante_id_1")
            return Resultado(
                [
                    camara
                    for camara in sorted(self.camaras.values(), key=lambda fila: fila.id)
                    if camara.restaurante_id == tenant
                ]
            )

        raise AssertionError(f"Consulta no soportada por la sesión falsa:\n{sentencia}")

    def _lecturas(
        self, sentencia: object, sql: str, params: dict[str, Any]
    ) -> list[Lectura]:
        """Filas de lecturas con los filtros, orden y límite que usa la API."""
        if "id_1" in params:
            ids = params["id_1"]
            return [lectura for lectura in self.lecturas if lectura.id in ids]
        camara_ids = params.get("camara_id_1")
        if isinstance(camara_ids, (list, tuple, set, frozenset)):
            filas = [lectura for lectura in self.lecturas if lectura.camara_id in camara_ids]
        else:
            filas = [lectura for lectura in self.lecturas if lectura.camara_id == camara_ids]
        if "distinct on" in sql:
            recientes: dict[int, Lectura] = {}
            for lectura in sorted(
                filas, key=lambda fila: fila.recibida_en, reverse=True
            ):
                recientes.setdefault(lectura.camara_id, lectura)
            return list(recientes.values())
        if "order by" in sql and "desc" in sql:
            filas = sorted(filas, key=lambda fila: fila.recibida_en, reverse=True)
        limite = getattr(sentencia, "_limit", None)
        return filas[:limite] if limite is not None else filas

    @staticmethod
    def _sumas_por_camara(lotes: list[Lote]) -> list[tuple[int, Decimal, Decimal]]:
        totales: dict[int, tuple[Decimal, Decimal]] = {}
        for lote in lotes:
            riesgo, inventario = totales.get(lote.camara_id, (Decimal(0), Decimal(0)))
            if lote.estado == "en_riesgo":
                riesgo += lote.costo_total_mxn
            if lote.estado != "merma":
                inventario += lote.costo_total_mxn
            totales[lote.camara_id] = (riesgo, inventario)
        return [
            (camara_id, riesgo, inventario)
            for camara_id, (riesgo, inventario) in totales.items()
        ]


def _camara(
    camara_id: int = 1,
    restaurante_id: int = 1,
    nombre: str = "Cámara",
    **cambios: object,
) -> Camara:
    base: dict[str, object] = {
        "id": camara_id,
        "restaurante_id": restaurante_id,
        "es_demo": False,
        "nombre": nombre,
        "rango_min_c": Decimal("-5.0"),
        "rango_max_c": Decimal("5.0"),
        "min_para_riesgo": 10,
        "min_para_merma": 60,
        "estado": "en_rango",
    }
    base.update(cambios)
    return Camara(**base)


def _sensor(
    sensor_id: str = "S-NUEVO",
    camara_id: int = 1,
    activo: bool = True,
    token: str = "token-viejo",
    ultima_lectura_en: datetime | None = None,
) -> Sensor:
    return Sensor(
        id=sensor_id,
        camara_id=camara_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        activo=activo,
        ultima_lectura_en=ultima_lectura_en,
    )


def _lectura(
    lectura_id: int,
    camara_id: int,
    sensor_id: str,
    recibida_en: datetime,
    temperatura_c: str = "1.4",
    puerta_abierta: bool = False,
) -> Lectura:
    return Lectura(
        id=lectura_id,
        camara_id=camara_id,
        sensor_id=sensor_id,
        ts=recibida_en,
        recibida_en=recibida_en,
        temperatura_c=Decimal(temperatura_c),
        humedad_pct=Decimal("88.0"),
        puerta_abierta=puerta_abierta,
        sospechosa=False,
    )


def _lote(camara_id: int = 1, lote_id: int = 1) -> Lote:
    return Lote(
        id=lote_id,
        producto="Robalo",
        camara_id=camara_id,
        cantidad=Decimal("2.00"),
        unidad="kg",
        costo_total_mxn=Decimal("500.00"),
        caducidad=date(2026, 11, 20),
        estado="ok",
    )


def _alerta(
    camara_id: int = 1,
    alerta_id: int = 1,
    tipo: str = "temperatura",
    cerrada_en: datetime | None = None,
) -> Alerta:
    return Alerta(
        id=alerta_id,
        camara_id=camara_id,
        tipo=tipo,
        abierta_en=datetime(2026, 11, 18, 19, 0, tzinfo=UTC),
        cerrada_en=cerrada_en,
        sms_enviados=1,
    )


def _cliente(sesion: SesionFalsa, restaurante_id: int | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    if restaurante_id is not None:
        app.dependency_overrides[get_restaurante_id] = lambda: restaurante_id
    return TestClient(app)


def _cliente_con_auth(
    monkeypatch: pytest.MonkeyPatch,
    sesion: SesionFalsa,
    usuario: Usuario,
) -> tuple[TestClient, dict[str, str]]:
    """Cliente con JWT real y auth encendida, para probar los roles."""
    monkeypatch.setenv("AUTH_REQUERIDA", "1")
    limpiar_cache_settings()
    sesion.usuarios[usuario.id] = usuario
    app = create_app()
    app.dependency_overrides[get_db] = lambda: sesion
    app.dependency_overrides[sesion_si_auth] = lambda: sesion
    return TestClient(app), {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture(autouse=True)
def _sin_cache_settings():
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


# --- Cámaras: alta ----------------------------------------------------------


def test_crear_camara_201_con_shape_completo_y_tenant():
    sesion = SesionFalsa()

    with _cliente(sesion, restaurante_id=7) as cliente:
        respuesta = cliente.post("/api/camaras", json=DATOS_CAMARA)

    assert respuesta.status_code == 201
    assert respuesta.json() == {
        "id": 1,
        "nombre": "Barra fría",
        "rango_min_c": -5.0,
        "rango_max_c": 5.0,
        "min_para_riesgo": 10,
        "min_para_merma": 60,
        "estado": "en_rango",
        "ultima_lectura": None,
        "valor_en_riesgo_mxn": 0.0,
        "valor_inventario_mxn": 0.0,
    }
    assert sesion.camaras[1].restaurante_id == 7
    assert sesion.camaras[1].es_demo is False


def test_crear_camara_acepta_rangos_con_un_decimal():
    sesion = SesionFalsa()

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/camaras", json={**DATOS_CAMARA, "rango_min_c": 4.0, "rango_max_c": 4.1}
        )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["rango_min_c"] == 4.0
    assert cuerpo["rango_max_c"] == 4.1


def test_crear_camara_permite_nombre_duplicado():
    sesion = SesionFalsa()

    with _cliente(sesion) as cliente:
        primera = cliente.post("/api/camaras", json=DATOS_CAMARA)
        segunda = cliente.post("/api/camaras", json=DATOS_CAMARA)
        listado = cliente.get("/api/camaras").json()

    assert primera.status_code == 201
    assert segunda.status_code == 201
    assert [camara["nombre"] for camara in listado] == ["Barra fría", "Barra fría"]
    assert [camara["valor_en_riesgo_mxn"] for camara in listado] == [0.0, 0.0]


@pytest.mark.parametrize(
    "cambios",
    [
        {"rango_min_c": 5.0, "rango_max_c": 2.0},
        {"rango_min_c": 2.0, "rango_max_c": 2.0},
        {"min_para_riesgo": 60, "min_para_merma": 60},
        {"min_para_riesgo": 60, "min_para_merma": 30},
        {"nombre": "A"},
        {"nombre": "  A  "},
        {"rango_min_c": -51.0},
        {"rango_max_c": 51.0},
        {"rango_min_c": 4.04},
        {"rango_max_c": 4.01},
        {"min_para_riesgo": 0},
        {"min_para_merma": 0},
        {"campo_desconocido": 1},
    ],
    ids=[
        "rango-invertido",
        "rango-igual",
        "merma-igual-riesgo",
        "merma-menor-riesgo",
        "nombre-corto",
        "nombre-corto-con-espacios",
        "min-fuera-de-limite",
        "max-fuera-de-limite",
        "min-dos-decimales",
        "max-dos-decimales",
        "riesgo-cero",
        "merma-cero",
        "campo-extra",
    ],
)
def test_crear_camara_invalida_regresa_422(cambios):
    sesion = SesionFalsa()
    datos = {**DATOS_CAMARA, **cambios}

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/camaras", json=datos)

    assert respuesta.status_code == 422
    assert sesion.camaras == {}


# --- Cámaras: edición -------------------------------------------------------


def test_actualizar_camara_cambia_solo_la_configuracion():
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch(
            "/api/camaras/1",
            json={"nombre": "  Congelador  ", "rango_max_c": -2.0, "min_para_merma": 90},
        )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Congelador"
    assert cuerpo["rango_max_c"] == -2.0
    assert cuerpo["min_para_merma"] == 90
    assert cuerpo["estado"] == "en_rango"
    camara = sesion.camaras[1]
    assert camara.nombre == "Congelador"
    assert camara.estado == "en_rango"


@pytest.mark.parametrize(
    "cambios",
    [
        {"estado": "critica"},
        {"ultima_lectura_id": 5},
        {"restaurante_id": 2},
    ],
    ids=["estado", "ultima-lectura", "restaurante"],
)
def test_actualizar_camara_rechaza_campos_de_sistema(cambios):
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/camaras/1", json=cambios)

    assert respuesta.status_code == 422
    assert sesion.camaras[1].estado == "en_rango"


@pytest.mark.parametrize(
    "cambios",
    [{"nombre": None}, {"rango_min_c": None}, {"min_para_merma": None}],
    ids=["nombre", "rango", "merma"],
)
def test_actualizar_camara_rechaza_nulos(cambios):
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/camaras/1", json=cambios)

    assert respuesta.status_code == 422
    assert sesion.camaras[1].nombre == "Cámara"


def test_actualizar_camara_valida_contra_lo_guardado():
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/camaras/1", json={"rango_max_c": -6.0})

    assert respuesta.status_code == 422
    assert "rango_min_c" in respuesta.json()["detail"][0]["msg"]


@pytest.mark.parametrize(
    "cambios",
    [{"rango_min_c": 4.04}, {"rango_max_c": 4.01}],
    ids=["min", "max"],
)
def test_actualizar_camara_rechaza_rangos_con_dos_decimales(cambios):
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/camaras/1", json=cambios)

    assert respuesta.status_code == 422
    assert sesion.camaras[1].rango_max_c == Decimal("5.0")


def test_actualizar_camara_de_otro_tenant_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(2, restaurante_id=2))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.patch("/api/camaras/2", json={"nombre": "Ajena"})

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Cámara no encontrada"


def test_patch_que_amplia_rango_cierra_alerta_y_limpia_ventana(monkeypatch):
    sesion = SesionFalsa()
    sesion.add(
        _camara(
            1,
            rango_min_c=Decimal("0.0"),
            rango_max_c=Decimal("4.0"),
            estado="alerta",
            fuera_de_rango_desde=datetime(2026, 11, 18, 18, 0, tzinfo=UTC),
            ultima_lectura_id=1,
        )
    )
    sesion.lecturas.append(
        _lectura(
            1,
            1,
            "S-A",
            datetime(2026, 11, 18, 18, 5, tzinfo=UTC),
            temperatura_c="6.0",
        )
    )
    alerta = _alerta(camara_id=1)
    sesion.alertas.append(alerta)
    publicados: list[tuple[str, dict[str, object], int]] = []
    monkeypatch.setattr(
        camaras_mod,
        "bus",
        SimpleNamespace(
            publicar=lambda evento, data, tenant: publicados.append((evento, data, tenant))
        ),
    )

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/camaras/1", json={"rango_max_c": 8.0})

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "en_rango"
    camara = sesion.camaras[1]
    assert camara.estado == "en_rango"
    assert camara.fuera_de_rango_desde is None
    assert alerta.cerrada_en is not None
    assert [evento for evento, _, _ in publicados] == ["alerta_cerrada"]
    assert publicados[0][2] == 1


def test_patch_que_estrecha_rango_pasa_la_camara_a_alerta():
    sesion = SesionFalsa()
    sesion.add(
        _camara(
            1,
            rango_min_c=Decimal("0.0"),
            rango_max_c=Decimal("4.0"),
            estado="en_rango",
            ultima_lectura_id=1,
        )
    )
    sesion.lecturas.append(
        _lectura(1, 1, "S-A", datetime(2026, 11, 18, 18, 5, tzinfo=UTC), temperatura_c="2.0")
    )

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/camaras/1", json={"rango_max_c": 1.0})

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "alerta"
    camara = sesion.camaras[1]
    assert camara.estado == "alerta"
    assert camara.fuera_de_rango_desde is not None
    assert sesion.alertas == []  # no se abre alerta: la decide la próxima lectura


def test_patch_sin_lecturas_cierra_alerta_y_deja_en_rango():
    sesion = SesionFalsa()
    sesion.add(_camara(1, estado="alerta", fuera_de_rango_desde=datetime.now(UTC)))
    alerta = _alerta(camara_id=1)
    sesion.alertas.append(alerta)

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/camaras/1", json={"min_para_riesgo": 20})

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "en_rango"
    assert sesion.camaras[1].fuera_de_rango_desde is None
    assert alerta.cerrada_en is not None


# --- Cámaras: baja ----------------------------------------------------------


def test_borrar_camara_sin_dependencias_regresa_204():
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.delete("/api/camaras/1")

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert sesion.camaras == {}
    assert len(sesion.eliminados) == 1


@pytest.mark.parametrize("dependencia", ["sensor", "lote", "lectura", "alerta"])
def test_borrar_camara_con_dependencias_regresa_409(dependencia):
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    if dependencia == "sensor":
        sesion.add(_sensor("S-UNO", camara_id=1))
    elif dependencia == "lote":
        sesion.lotes.append(_lote(camara_id=1))
    elif dependencia == "lectura":
        sesion.lecturas.append(_lectura(1, 1, "S-UNO", datetime.now(UTC)))
    else:
        sesion.alertas.append(_alerta(camara_id=1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.delete("/api/camaras/1")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_CAMARA_CON_DATOS
    assert 1 in sesion.camaras
    assert sesion.eliminados == []


def test_borrar_camara_de_otro_tenant_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(2, restaurante_id=2))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.delete("/api/camaras/2")

    assert respuesta.status_code == 404
    assert 2 in sesion.camaras


# --- Sensores: alta, token y telemetría -------------------------------------


def test_crear_sensor_entrega_token_una_vez_y_guarda_solo_el_hash():
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/camaras/1/sensores")
        listado = cliente.get("/api/sensores").json()

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    ident = cuerpo["sensor"]["id"]
    assert cuerpo["sensor"] == {"id": ident, "camara_id": 1, "activo": True}
    token = cuerpo["token"]
    assert len(token) >= 32
    assert sesion.sensores[ident].token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(listado)
    assert "token_hash" not in json.dumps(listado)
    assert listado == [
        {
            "id": ident,
            "camara_id": 1,
            "activo": True,
            "camara_nombre": "Cámara",
            "ultima_lectura": None,
        }
    ]


def test_crear_sensor_genera_s_mas_ocho_hex_e_ignora_el_id_del_cliente():
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/camaras/1/sensores", json={"id": "S-PES-01"})

    ident = respuesta.json()["sensor"]["id"]
    assert respuesta.status_code == 201
    assert ident != "S-PES-01"
    assert ident.startswith("S-")
    assert len(ident) == 10
    assert all(caracter in "0123456789abcdef" for caracter in ident[2:])


def test_crear_sensor_en_camara_ajena_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(2, restaurante_id=2))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.post("/api/camaras/2/sensores")

    assert respuesta.status_code == 404
    assert sesion.sensores == {}


def test_telemetria_acepta_el_token_creado_y_la_rotacion_invalida_el_anterior():
    sesion = SesionFalsa()

    with _cliente(sesion) as cliente:
        camara = cliente.post("/api/camaras", json=DATOS_CAMARA).json()
        creado = cliente.post(f"/api/camaras/{camara['id']}/sensores").json()
        ident = creado["sensor"]["id"]
        token_viejo = creado["token"]
        payload = _payload(ident, camara["id"])

        primera = cliente.post(
            "/api/telemetria",
            json=payload,
            headers={"Authorization": f"Bearer {token_viejo}"},
        )
        rotado = cliente.post(f"/api/sensores/{ident}/rotar-token").json()
        token_nuevo = rotado["token"]
        con_viejo = cliente.post(
            "/api/telemetria",
            json=payload,
            headers={"Authorization": f"Bearer {token_viejo}"},
        )
        con_nuevo = cliente.post(
            "/api/telemetria",
            json=payload,
            headers={"Authorization": f"Bearer {token_nuevo}"},
        )

    assert primera.status_code == 202
    assert rotado["sensor"] == {"id": ident, "camara_id": 1, "activo": True}
    assert token_nuevo != token_viejo
    assert con_viejo.status_code == 401
    assert con_nuevo.status_code == 202
    assert sesion.sensores[ident].token_hash == hashlib.sha256(
        token_nuevo.encode()
    ).hexdigest()
    assert sesion.sensores[ident].ultima_lectura_en is not None


def test_desactivar_sensor_bloquea_la_telemetria_con_403():
    sesion = SesionFalsa()

    with _cliente(sesion) as cliente:
        camara = cliente.post("/api/camaras", json=DATOS_CAMARA).json()
        creado = cliente.post(f"/api/camaras/{camara['id']}/sensores").json()
        ident = creado["sensor"]["id"]
        token = creado["token"]
        desactivado = cliente.patch(f"/api/sensores/{ident}", json={"activo": False})
        telemetria = cliente.post(
            "/api/telemetria",
            json=_payload(ident, camara["id"]),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert desactivado.status_code == 200
    assert desactivado.json() == {"id": ident, "camara_id": 1, "activo": False}
    assert telemetria.status_code == 403
    assert "inactivo" in telemetria.json()["detail"]


# --- Sensores: listado y baja -----------------------------------------------


def test_listar_sensores_usa_una_consulta_y_la_cache_de_ultima_lectura():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(
        _sensor(
            "S-A",
            camara_id=1,
            ultima_lectura_en=datetime(2026, 11, 18, 19, 0, tzinfo=UTC),
        )
    )
    sesion.add(_sensor("S-B", camara_id=1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.get("/api/sensores")

    assert respuesta.status_code == 200
    assert respuesta.json() == [
        {
            "id": "S-A",
            "camara_id": 1,
            "activo": True,
            "camara_nombre": "Cámara",
            "ultima_lectura": "2026-11-18T19:00:00+00:00",
        },
        {
            "id": "S-B",
            "camara_id": 1,
            "activo": True,
            "camara_nombre": "Cámara",
            "ultima_lectura": None,
        },
    ]
    # Una sola consulta de sensores+cámara; la última lectura sale de la caché.
    assert len(sesion.consultas) == 1


def test_listar_sensores_aisla_por_tenant():
    sesion = SesionFalsa()
    sesion.add(_camara(1, restaurante_id=1, nombre="Propia"))
    sesion.add(_camara(2, restaurante_id=2, nombre="Ajena"))
    sesion.add(_sensor("S-PROPIO", camara_id=1))
    sesion.add(_sensor("S-AJENO", camara_id=2))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.get("/api/sensores")

    assert [sensor["id"] for sensor in respuesta.json()] == ["S-PROPIO"]


def test_borrar_sensor_sin_lecturas_regresa_204():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_sensor("S-NUEVO", camara_id=1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.delete("/api/sensores/S-NUEVO")

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert sesion.sensores == {}


def test_borrar_sensor_con_lecturas_regresa_409():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_sensor("S-NUEVO", camara_id=1))
    sesion.lecturas.append(_lectura(1, 1, "S-NUEVO", datetime.now(UTC)))

    with _cliente(sesion) as cliente:
        respuesta = cliente.delete("/api/sensores/S-NUEVO")

    assert respuesta.status_code == 409
    assert "desactívalo" in respuesta.json()["detail"]
    assert "S-NUEVO" in sesion.sensores


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("patch", "/api/sensores/S-AJENO", {"activo": False}),
        ("post", "/api/sensores/S-AJENO/rotar-token", None),
        ("delete", "/api/sensores/S-AJENO", None),
    ],
)
def test_sensores_de_otro_tenant_regresan_404(metodo, ruta, cuerpo):
    sesion = SesionFalsa()
    sesion.add(_camara(2, restaurante_id=2))
    sesion.add(_sensor("S-AJENO", camara_id=2))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = getattr(cliente, metodo)(ruta, json=cuerpo) if cuerpo else getattr(
            cliente, metodo
        )(ruta)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Sensor no encontrado"
    assert sesion.sensores["S-AJENO"].activo is True


# --- Roles ------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["jefe_cocina", "gerente"])
def test_escritura_de_camaras_exige_rol_dueno(monkeypatch, rol):
    usuario = Usuario(
        id=9,
        restaurante_id=1,
        usuario=f"usuario-{rol}",
        password_hash="hash",
        rol=rol,
    )
    sesion = SesionFalsa()
    cliente, headers = _cliente_con_auth(monkeypatch, sesion, usuario)

    with cliente:
        crear = cliente.post("/api/camaras", json=DATOS_CAMARA, headers=headers)
        borrar = cliente.delete("/api/camaras/1", headers=headers)

    assert crear.status_code == 403
    assert borrar.status_code == 403
    assert sesion.camaras == {}


def test_dueno_puede_crear_y_listar(monkeypatch):
    usuario = Usuario(
        id=7,
        restaurante_id=1,
        usuario="dueno@norte.mx",
        password_hash="hash",
        rol="dueno",
    )
    sesion = SesionFalsa()
    cliente, headers = _cliente_con_auth(monkeypatch, sesion, usuario)

    with cliente:
        crear = cliente.post("/api/camaras", json=DATOS_CAMARA, headers=headers)
        listado = cliente.get("/api/sensores", headers=headers)

    assert crear.status_code == 201
    assert sesion.camaras[1].restaurante_id == 1
    assert listado.status_code == 200
    assert listado.json() == []


def test_listar_sensores_permite_roles_de_lectura(monkeypatch):
    usuario = Usuario(
        id=8,
        restaurante_id=1,
        usuario="jefe",
        password_hash="hash",
        rol="jefe_cocina",
    )
    sesion = SesionFalsa()
    cliente, headers = _cliente_con_auth(monkeypatch, sesion, usuario)

    with cliente:
        respuesta = cliente.get("/api/sensores", headers=headers)

    assert respuesta.status_code == 200
    assert respuesta.json() == []
