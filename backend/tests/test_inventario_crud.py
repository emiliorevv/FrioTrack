"""Pruebas del CRUD de lotes y la marca manual de merma, con sesión falsa."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import limpiar_cache_settings
from app.core.auth import crear_token, get_restaurante_id, sesion_si_auth
from app.db.models import Camara, Lote, Usuario
from app.db.session import get_db
from app.main import create_app

DATOS_LOTE = {
    "producto": "Robalo fresco",
    "camara_id": 1,
    "cantidad": "12.50",
    "unidad": "kg",
    "costo_total_mxn": "3240.50",
    "caducidad": "2026-11-20",
}

MENSAJE_LOTE_EN_MERMA = (
    "El lote ya está en merma; no se puede eliminar del historial."
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


class SesionFalsa:
    """Sesión en memoria para lotes, cámaras y usuarios."""

    def __init__(self) -> None:
        self.camaras: dict[int, Camara] = {}
        self.lotes: dict[int, Lote] = {}
        self.usuarios: dict[int, Usuario] = {}
        self.agregados: list[object] = []
        self.eliminados: list[object] = []
        self.consultas: list[object] = []
        self.commits = 0
        self.flushes = 0
        self.rollbacks = 0
        self.refreshes: list[object] = []
        self.siguiente_lote = 1

    # --- escritura ---------------------------------------------------------

    def add(self, fila: object) -> None:
        self.agregados.append(fila)
        if isinstance(fila, Lote):
            if fila.id is None:
                fila.id = self.siguiente_lote
                self.siguiente_lote += 1
            else:
                self.siguiente_lote = max(self.siguiente_lote, fila.id + 1)
            self.lotes[fila.id] = fila
        elif isinstance(fila, Camara):
            self.camaras[fila.id] = fila

    def flush(self) -> None:
        self.flushes += 1
        for fila in self.agregados:
            if isinstance(fila, Lote) and fila.id is None:
                fila.id = self.siguiente_lote
                self.siguiente_lote += 1
                self.lotes[fila.id] = fila

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, fila: object) -> None:
        self.refreshes.append(fila)

    def delete(self, fila: object) -> None:
        self.eliminados.append(fila)
        if isinstance(fila, Lote):
            self.lotes.pop(fila.id, None)
        elif isinstance(fila, Camara):
            self.camaras.pop(fila.id, None)

    # --- lectura -----------------------------------------------------------

    def get(self, modelo: object, ident: object, **_kwargs: object) -> object | None:
        if modelo is Camara:
            return self.camaras.get(ident)  # type: ignore[arg-type]
        if modelo is Lote:
            return self.lotes.get(ident)  # type: ignore[arg-type]
        if modelo is Usuario:
            return self.usuarios.get(ident)  # type: ignore[arg-type]
        return None

    def scalar(self, sentencia: object) -> object | None:
        self.consultas.append(sentencia)
        return None

    def scalars(self, sentencia: object) -> Resultado:
        self.consultas.append(sentencia)
        return Resultado([])

    def execute(self, sentencia: object) -> Resultado:
        self.consultas.append(sentencia)
        sql = str(sentencia).lower()
        params = sentencia.compile().params  # type: ignore[attr-defined]

        if "from camaras" in sql:
            tenant = params.get("restaurante_id_1")
            return Resultado(
                [
                    camara
                    for camara in sorted(self.camaras.values(), key=lambda fila: fila.id)
                    if camara.restaurante_id == tenant
                ]
            )

        if "group by" in sql and "from lotes" in sql:
            ids = params.get("camara_id_1")
            return Resultado(self._sumas_por_camara(set(ids)))

        if "from lotes" in sql:
            camaras = {camara.id: camara.restaurante_id for camara in self.camaras.values()}
            tenant = params.get("restaurante_id_1")
            filas = [
                lote
                for lote in self.lotes.values()
                if camaras.get(lote.camara_id) == tenant
            ]
            if "camara_id_1" in params:
                filas = [lote for lote in filas if lote.camara_id == params["camara_id_1"]]
            if "estado_1" in params:
                filas = [lote for lote in filas if lote.estado == params["estado_1"]]
            return Resultado(sorted(filas, key=lambda fila: fila.id))

        if "from lecturas" in sql:
            return Resultado([])

        raise AssertionError(f"Consulta no soportada por la sesión falsa:\n{sentencia}")

    def _sumas_por_camara(self, ids: set[int]) -> list[tuple[int, Decimal, Decimal]]:
        totales: dict[int, tuple[Decimal, Decimal]] = {}
        for lote in self.lotes.values():
            if lote.camara_id not in ids:
                continue
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
) -> Camara:
    return Camara(
        id=camara_id,
        restaurante_id=restaurante_id,
        es_demo=False,
        nombre=nombre,
        rango_min_c=Decimal("0.0"),
        rango_max_c=Decimal("4.0"),
        min_para_riesgo=10,
        min_para_merma=60,
        estado="en_rango",
    )


def _lote(
    lote_id: int = 1,
    camara_id: int = 1,
    producto: str = "Robalo fresco",
    cantidad: str = "12.50",
    costo_total_mxn: str = "3240.50",
    estado: str = "ok",
    merma_en: datetime | None = None,
) -> Lote:
    return Lote(
        id=lote_id,
        producto=producto,
        camara_id=camara_id,
        cantidad=Decimal(cantidad),
        unidad="kg",
        costo_total_mxn=Decimal(costo_total_mxn),
        caducidad=date(2026, 11, 20),
        estado=estado,
        merma_en=merma_en,
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


# --- Alta -------------------------------------------------------------------


def test_crear_lote_201_con_shape_y_tenant():
    sesion = SesionFalsa()
    sesion.add(_camara(1, restaurante_id=7))

    with _cliente(sesion, restaurante_id=7) as cliente:
        respuesta = cliente.post(
            "/api/lotes", json={**DATOS_LOTE, "producto": "  Robalo fresco  "}
        )

    assert respuesta.status_code == 201
    assert respuesta.json() == {
        "id": 1,
        "producto": "Robalo fresco",
        "camara_id": 1,
        "cantidad": 12.5,
        "unidad": "kg",
        "costo_total_mxn": 3240.5,
        "caducidad": "2026-11-20",
        "estado": "ok",
        "merma_en": None,
    }
    lote = sesion.lotes[1]
    assert lote.estado == "ok"
    assert lote.merma_en is None


def test_crear_lote_permite_caducidad_pasada():
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.post(
            "/api/lotes", json={**DATOS_LOTE, "caducidad": "2020-01-01"}
        )

    assert respuesta.status_code == 201
    assert respuesta.json()["caducidad"] == "2020-01-01"


@pytest.mark.parametrize(
    "cambios",
    [
        {"producto": "A"},
        {"producto": "  A  "},
        {"cantidad": 0},
        {"cantidad": "-1"},
        {"cantidad": "1.234"},
        {"unidad": "lb"},
        {"unidad": "KG"},
        {"costo_total_mxn": "-0.01"},
        {"camara_id": 0},
        {"caducidad": "2026-02-30"},
        {"estado": "merma"},
        {"merma_en": "2026-11-16T00:00:00Z"},
        {"restaurante_id": 2},
    ],
    ids=[
        "producto-corto",
        "producto-corto-con-espacios",
        "cantidad-cero",
        "cantidad-negativa",
        "cantidad-tres-decimales",
        "unidad-invalida",
        "unidad-mayusculas",
        "costo-negativo",
        "camara-cero",
        "fecha-invalida",
        "estado-extra",
        "merma-extra",
        "restaurante-extra",
    ],
)
def test_crear_lote_invalido_regresa_422(cambios):
    sesion = SesionFalsa()
    sesion.add(_camara(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/lotes", json={**DATOS_LOTE, **cambios})

    assert respuesta.status_code == 422
    assert sesion.lotes == {}


def test_crear_lote_en_camara_inexistente_regresa_404():
    sesion = SesionFalsa()

    with _cliente(sesion) as cliente:
        respuesta = cliente.post("/api/lotes", json=DATOS_LOTE)

    assert respuesta.status_code == 404
    assert sesion.lotes == {}


def test_crear_lote_en_camara_de_otro_tenant_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(6, restaurante_id=2))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.post("/api/lotes", json={**DATOS_LOTE, "camara_id": 6})

    assert respuesta.status_code == 404
    assert sesion.lotes == {}


# --- Edición ----------------------------------------------------------------


def test_actualizar_lote_parcial_conserva_lo_demas():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch(
            "/api/lotes/1", json={"producto": "  Pulpo  ", "cantidad": "5.50"}
        )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["producto"] == "Pulpo"
    assert cuerpo["cantidad"] == 5.5
    assert cuerpo["costo_total_mxn"] == 3240.5
    assert cuerpo["caducidad"] == "2026-11-20"
    assert cuerpo["estado"] == "ok"


@pytest.mark.parametrize(
    "cambios",
    [
        {"estado": "merma"},
        {"merma_en": "2026-11-16T00:00:00Z"},
        {"restaurante_id": 2},
    ],
    ids=["estado", "merma", "restaurante"],
)
def test_actualizar_lote_rechaza_campos_de_sistema(cambios):
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/lotes/1", json=cambios)

    assert respuesta.status_code == 422
    assert sesion.lotes[1].estado == "ok"


@pytest.mark.parametrize(
    "cambios",
    [{"producto": None}, {"cantidad": None}, {"unidad": None}],
    ids=["producto", "cantidad", "unidad"],
)
def test_actualizar_lote_rechaza_nulos(cambios):
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/lotes/1", json=cambios)

    assert respuesta.status_code == 422


def test_actualizar_lote_de_otro_tenant_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(6, restaurante_id=2))
    sesion.add(_lote(1, camara_id=6))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.patch("/api/lotes/1", json={"producto": "Ajeno"})

    assert respuesta.status_code == 404
    assert sesion.lotes[1].producto == "Robalo fresco"


def test_mover_lote_a_otra_camara_del_mismo_tenant():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_camara(2, nombre="Carnes"))
    sesion.add(_lote(1))

    with _cliente(sesion) as cliente:
        respuesta = cliente.patch("/api/lotes/1", json={"camara_id": 2})

    assert respuesta.status_code == 200
    assert respuesta.json()["camara_id"] == 2
    assert sesion.lotes[1].camara_id == 2


def test_mover_lote_a_camara_de_otro_tenant_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_camara(6, restaurante_id=2))
    sesion.add(_lote(1))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.patch("/api/lotes/1", json={"camara_id": 6})

    assert respuesta.status_code == 404
    assert sesion.lotes[1].camara_id == 1


# --- Baja y merma -----------------------------------------------------------


@pytest.mark.parametrize("estado", ["ok", "en_riesgo"])
def test_borrar_lote_sin_merma_regresa_204(estado):
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1, estado=estado))

    with _cliente(sesion) as cliente:
        respuesta = cliente.delete("/api/lotes/1")

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert sesion.lotes == {}


def test_borrar_lote_en_merma_regresa_409():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1, estado="merma", merma_en=datetime.now(UTC)))

    with _cliente(sesion) as cliente:
        respuesta = cliente.delete("/api/lotes/1")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_LOTE_EN_MERMA
    assert 1 in sesion.lotes


def test_borrar_lote_de_otro_tenant_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(6, restaurante_id=2))
    sesion.add(_lote(1, camara_id=6))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.delete("/api/lotes/1")

    assert respuesta.status_code == 404
    assert 1 in sesion.lotes


def test_marcar_merma_marca_y_es_idempotente():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1))

    with _cliente(sesion) as cliente:
        primera = cliente.post("/api/lotes/1/merma")
        segunda = cliente.post("/api/lotes/1/merma")
        listado = cliente.get("/api/lotes").json()

    assert primera.status_code == 200
    assert primera.json()["estado"] == "merma"
    assert primera.json()["merma_en"] is not None
    assert segunda.status_code == 200
    assert segunda.json()["merma_en"] == primera.json()["merma_en"]
    assert sesion.commits == 1  # la segunda llamada no vuelve a escribir
    assert listado[0]["estado"] == "merma"
    assert listado[0]["merma_en"] == primera.json()["merma_en"]


def test_marcar_merma_de_otro_tenant_regresa_404():
    sesion = SesionFalsa()
    sesion.add(_camara(6, restaurante_id=2))
    sesion.add(_lote(1, camara_id=6))

    with _cliente(sesion, restaurante_id=1) as cliente:
        respuesta = cliente.post("/api/lotes/1/merma")

    assert respuesta.status_code == 404
    assert sesion.lotes[1].estado == "ok"


# --- Consulta ---------------------------------------------------------------


def test_get_lotes_filtra_por_camara_estado_y_tenant():
    sesion = SesionFalsa()
    sesion.add(_camara(1, restaurante_id=1))
    sesion.add(_camara(2, restaurante_id=1))
    sesion.add(_camara(6, restaurante_id=2))
    sesion.add(_lote(1, camara_id=1, estado="ok"))
    sesion.add(_lote(2, camara_id=1, estado="en_riesgo"))
    sesion.add(_lote(3, camara_id=2, estado="ok"))
    sesion.add(_lote(4, camara_id=6, estado="ok"))

    with _cliente(sesion, restaurante_id=1) as cliente:
        todos = cliente.get("/api/lotes").json()
        por_camara = cliente.get("/api/lotes", params={"camara_id": 1}).json()
        por_estado = cliente.get("/api/lotes", params={"estado": "ok"}).json()

    assert [lote["id"] for lote in todos] == [1, 2, 3]
    assert [lote["id"] for lote in por_camara] == [1, 2]
    assert [lote["id"] for lote in por_estado] == [1, 3]


def test_get_camaras_suma_inventario_y_riesgo_de_lotes_nuevos():
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1, camara_id=1, costo_total_mxn="500.00", estado="ok"))
    sesion.add(_lote(2, camara_id=1, costo_total_mxn="300.00", estado="en_riesgo"))
    sesion.add(_lote(3, camara_id=1, costo_total_mxn="100.00", estado="merma"))

    with _cliente(sesion) as cliente:
        camaras = cliente.get("/api/camaras").json()

    assert camaras[0]["valor_inventario_mxn"] == 800.0
    assert camaras[0]["valor_en_riesgo_mxn"] == 300.0


# --- Roles ------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["dueno", "jefe_cocina"])
def test_roles_de_escritura_pueden_crear_lote(monkeypatch, rol):
    usuario = Usuario(
        id=9,
        restaurante_id=1,
        usuario=f"usuario-{rol}",
        password_hash="hash",
        rol=rol,
    )
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    cliente, headers = _cliente_con_auth(monkeypatch, sesion, usuario)

    with cliente:
        respuesta = cliente.post("/api/lotes", json=DATOS_LOTE, headers=headers)

    assert respuesta.status_code == 201
    assert sesion.lotes[1].producto == "Robalo fresco"


def test_gerente_no_puede_escribir_en_inventario(monkeypatch):
    usuario = Usuario(
        id=8,
        restaurante_id=1,
        usuario="gerente",
        password_hash="hash",
        rol="gerente",
    )
    sesion = SesionFalsa()
    sesion.add(_camara(1))
    sesion.add(_lote(1))
    cliente, headers = _cliente_con_auth(monkeypatch, sesion, usuario)

    with cliente:
        crear = cliente.post("/api/lotes", json=DATOS_LOTE, headers=headers)
        editar = cliente.patch(
            "/api/lotes/1", json={"producto": "Otro"}, headers=headers
        )
        merma = cliente.post("/api/lotes/1/merma", headers=headers)
        borrar = cliente.delete("/api/lotes/1", headers=headers)
        listar = cliente.get("/api/lotes", headers=headers)

    assert crear.status_code == 403
    assert editar.status_code == 403
    assert merma.status_code == 403
    assert borrar.status_code == 403
    assert listar.status_code == 200
    assert sesion.lotes[1].producto == "Robalo fresco"
