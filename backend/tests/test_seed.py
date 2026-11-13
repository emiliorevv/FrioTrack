"""Pruebas del seed y de los hashes; no tocan base de datos, disco ni red."""

import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.config import limpiar_cache_settings
from app.core.security import verify_password
from app.db.models import Camara, Lote, Sensor, Usuario
from app.db.seed import cargar_seed, construir_seed

TOKENS = {
    "S-PES-01": "token-pescados",
    "S-CAR-01": "token-carnes",
    "S-LAC-01": "token-lacteos",
    "S-VER-01": "token-verduras",
    "S-CON-01": "token-congelador",
}


@pytest.fixture(autouse=True)
def _settings_sin_cache():
    """Aísla cada prueba de la configuración cacheada y del .env local."""
    limpiar_cache_settings()
    yield
    limpiar_cache_settings()


def test_construir_seed_arma_las_cinco_camaras():
    camaras, _, _, _ = construir_seed(sensor_tokens=TOKENS, password="demo")

    assert [c.id for c in camaras] == [1, 2, 3, 4, 5]
    assert [c.nombre for c in camaras] == [
        "Pescados y mariscos",
        "Carnes y aves",
        "Lácteos",
        "Verduras y frutas",
        "Congelador",
    ]
    assert [float(c.rango_min_c) for c in camaras] == [0.0, 0.0, 1.0, 4.0, -22.0]
    assert [float(c.rango_max_c) for c in camaras] == [2.0, 4.0, 4.0, 8.0, -18.0]
    assert [(c.min_para_riesgo, c.min_para_merma) for c in camaras] == [
        (10, 60),
        (15, 120),
        (20, 180),
        (30, 240),
        (20, 120),
    ]
    assert all(c.estado == "en_rango" for c in camaras)
    assert all(c.fuera_de_rango_desde is None and c.ultima_lectura_id is None for c in camaras)


def test_construir_seed_arma_un_sensor_por_camara_con_token_hasheado():
    _, sensores, _, _ = construir_seed(sensor_tokens=TOKENS, password="demo")

    assert {s.id: s.camara_id for s in sensores} == {
        "S-PES-01": 1,
        "S-CAR-01": 2,
        "S-LAC-01": 3,
        "S-VER-01": 4,
        "S-CON-01": 5,
    }
    assert all(s.activo for s in sensores)
    for sensor in sensores:
        token = TOKENS[sensor.id]
        assert sensor.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert len(sensor.token_hash) == 64
        # El token en claro nunca queda guardado.
        assert sensor.token_hash != token
        assert token not in sensor.token_hash


def test_construir_seed_falla_si_faltan_todos_los_tokens():
    with pytest.raises(RuntimeError, match="SENSOR_TOKENS") as error:
        construir_seed(sensor_tokens={}, password="demo")

    for sensor_id in TOKENS:
        assert sensor_id in str(error.value)


def test_construir_seed_falla_con_un_mapa_incompleto_de_tokens():
    incompletos = {
        sensor_id: token for sensor_id, token in TOKENS.items() if sensor_id != "S-LAC-01"
    }

    with pytest.raises(RuntimeError, match="SENSOR_TOKENS") as error:
        construir_seed(sensor_tokens=incompletos, password="demo")

    assert "S-LAC-01" in str(error.value)
    assert "S-PES-01" not in str(error.value)


def test_construir_seed_lee_sensor_tokens_del_entorno(monkeypatch):
    monkeypatch.setenv("SENSOR_TOKENS", json.dumps(TOKENS))

    _, sensores, _, _ = construir_seed(password="demo")

    assert {s.token_hash for s in sensores} == {
        hashlib.sha256(token.encode("utf-8")).hexdigest() for token in TOKENS.values()
    }


def test_construir_seed_sin_password_lanza_error(monkeypatch):
    monkeypatch.setenv("SEED_PASSWORD", "")

    with pytest.raises(RuntimeError, match="SEED_PASSWORD"):
        construir_seed(sensor_tokens=TOKENS)


def test_construir_seed_arma_los_quince_lotes():
    _, _, lotes, _ = construir_seed(sensor_tokens=TOKENS, password="demo")

    assert len(lotes) == 15
    por_camara = Counter(lote.camara_id for lote in lotes)
    assert set(por_camara) == {1, 2, 3, 4, 5}
    assert all(2 <= cantidad <= 3 for cantidad in por_camara.values())
    assert all(lote.estado == "ok" and lote.merma_en is None for lote in lotes)

    hoy = date.today()
    assert all(hoy <= lote.caducidad <= hoy + timedelta(days=60) for lote in lotes)

    robalo = next(lote for lote in lotes if lote.producto == "Robalo fresco")
    assert robalo.camara_id == 1
    assert robalo.cantidad == Decimal("12.00")
    assert robalo.unidad == "kg"
    assert robalo.costo_total_mxn == Decimal("3240.00")

    papas = next(lote for lote in lotes if lote.producto == "Papas congeladas")
    assert papas.camara_id == 5
    assert papas.costo_total_mxn == Decimal("520.00")


def test_construir_seed_arma_los_dos_usuarios_con_password_verificable():
    _, _, _, usuarios = construir_seed(sensor_tokens=TOKENS, password="demo")

    por_nombre = {u.usuario: u for u in usuarios}
    assert set(por_nombre) == {"jefe", "gerente"}
    assert por_nombre["jefe"].rol == "jefe_cocina"
    assert por_nombre["gerente"].rol == "gerente"
    assert all(u.password_hash.startswith("pbkdf2_sha256$") for u in usuarios)
    assert all(u.password_hash != "demo" for u in usuarios)
    assert verify_password("demo", por_nombre["jefe"].password_hash)
    assert not verify_password("incorrecta", por_nombre["jefe"].password_hash)


class FakeSession:
    """Sesión falsa: registra llamadas sin abrir conexión ni tocar una base."""

    def __init__(self, hay_camaras: bool = False) -> None:
        self.hay_camaras = hay_camaras
        self.agregados: list[object] = []
        self.flushes = 0
        self.commits = 0

    def scalar(self, _sentencia: object) -> int | None:
        return 1 if self.hay_camaras else None

    def add_all(self, filas: list[object]) -> None:
        self.agregados.extend(filas)

    def flush(self) -> None:
        self.flushes += 1

    def commit(self) -> None:
        self.commits += 1


def test_cargar_seed_inserta_todo_y_hace_commit():
    sesion = FakeSession()

    assert cargar_seed(sesion, sensor_tokens=TOKENS, password="demo") is True
    assert sesion.flushes == 1
    assert sesion.commits == 1
    assert len(sesion.agregados) == 5 + 5 + 15 + 2
    assert sum(isinstance(fila, Camara) for fila in sesion.agregados) == 5
    assert sum(isinstance(fila, Sensor) for fila in sesion.agregados) == 5
    assert sum(isinstance(fila, Lote) for fila in sesion.agregados) == 15
    assert sum(isinstance(fila, Usuario) for fila in sesion.agregados) == 2


def test_cargar_seed_es_idempotente_si_ya_hay_camaras():
    sesion = FakeSession(hay_camaras=True)

    assert cargar_seed(sesion, sensor_tokens=TOKENS, password="demo") is False
    assert sesion.agregados == []
    assert sesion.flushes == 0
    assert sesion.commits == 0
