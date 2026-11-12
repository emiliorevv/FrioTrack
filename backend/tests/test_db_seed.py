"""Pruebas del esquema, los datos semilla y el hash de contraseñas."""

import hashlib
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password, verify_password
from app.db.models import Alerta, Camara, Lote, Sensor, Usuario
from app.db.seed import cargar_seed

TABLAS_ESPERADAS = {
    "camaras",
    "sensores",
    "lecturas",
    "lotes",
    "alertas",
    "usuarios",
    "logs_acceso",
    "alertas_seguridad",
    "ips_bloqueadas",
}


def test_se_crean_las_nueve_tablas(db_session):
    assert set(inspect(db_session.bind).get_table_names()) == TABLAS_ESPERADAS


def test_seed_carga_las_cinco_camaras(db_session):
    assert cargar_seed(db_session, sensor_tokens={}, password="demo") is True

    camaras = db_session.scalars(select(Camara).order_by(Camara.id)).all()
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


def test_seed_carga_un_sensor_por_camara_con_token_hasheado(db_session):
    assert cargar_seed(db_session, sensor_tokens={}, password="demo") is True

    sensores = {sensor.id: sensor for sensor in db_session.scalars(select(Sensor))}
    assert {sid: sensor.camara_id for sid, sensor in sensores.items()} == {
        "S-PES-01": 1,
        "S-CAR-01": 2,
        "S-LAC-01": 3,
        "S-VER-01": 4,
        "S-CON-01": 5,
    }
    assert all(sensor.activo for sensor in sensores.values())
    # Sin mapa de tokens se usa el fallback de desarrollo, pero nunca se guarda en claro.
    assert sensores["S-PES-01"].token_hash == hashlib.sha256(
        b"dev-token-S-PES-01"
    ).hexdigest()
    assert all(len(sensor.token_hash) == 64 for sensor in sensores.values())


def test_seed_respeta_el_mapa_de_tokens(db_session):
    tokens = {"S-PES-01": "token-real-de-pescados"}
    assert cargar_seed(db_session, sensor_tokens=tokens, password="demo") is True

    sensor = db_session.get(Sensor, "S-PES-01")
    assert sensor.token_hash == hashlib.sha256(b"token-real-de-pescados").hexdigest()
    assert sensor.token_hash != "token-real-de-pescados"


def test_seed_carga_entre_trece_y_quince_lotes(db_session):
    assert cargar_seed(db_session, sensor_tokens={}, password="demo") is True

    lotes = db_session.scalars(select(Lote)).all()
    assert 13 <= len(lotes) <= 15
    por_camara = Counter(lote.camara_id for lote in lotes)
    assert set(por_camara) == {1, 2, 3, 4, 5}
    assert all(2 <= cantidad <= 3 for cantidad in por_camara.values())
    assert all(lote.estado == "ok" and lote.merma_en is None for lote in lotes)

    robalo = next(lote for lote in lotes if lote.producto == "Robalo fresco")
    assert robalo.cantidad == Decimal("12.00")
    assert robalo.unidad == "kg"
    assert robalo.costo_total_mxn == Decimal("3240.00")


def test_seed_carga_los_dos_usuarios_con_rol_y_password(db_session):
    assert cargar_seed(db_session, sensor_tokens={}, password="demo") is True

    usuarios = {usuario.usuario: usuario for usuario in db_session.scalars(select(Usuario))}
    assert usuarios["jefe"].rol == "jefe_cocina"
    assert usuarios["gerente"].rol == "gerente"
    assert usuarios["jefe"].password_hash != "demo"
    assert usuarios["jefe"].password_hash.startswith("pbkdf2_sha256$")
    assert verify_password("demo", usuarios["jefe"].password_hash)
    assert not verify_password("incorrecta", usuarios["jefe"].password_hash)


def test_seed_es_idempotente(db_session):
    assert cargar_seed(db_session, sensor_tokens={}, password="demo") is True
    assert cargar_seed(db_session, sensor_tokens={}, password="otra") is False

    for modelo, esperado in ((Camara, 5), (Sensor, 5), (Lote, 15), (Usuario, 2)):
        assert db_session.scalar(select(func.count()).select_from(modelo)) == esperado


def test_indice_unico_parcial_de_alertas(db_session):
    assert cargar_seed(db_session, sensor_tokens={}, password="demo") is True

    # Una cerrada y una abierta del mismo tipo sí conviven.
    db_session.add(
        Alerta(camara_id=1, tipo="temperatura", cerrada_en=datetime.now(UTC))
    )
    db_session.add(Alerta(camara_id=1, tipo="temperatura"))
    db_session.commit()

    # Una segunda alerta abierta de la misma cámara y tipo debe fallar.
    db_session.add(Alerta(camara_id=1, tipo="temperatura"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Otro tipo de alerta abierta en la misma cámara sí se permite.
    db_session.add(Alerta(camara_id=1, tipo="puerta"))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Alerta)) == 3


def test_hash_password_usa_salt_aleatorio_y_verifica():
    primer_hash = hash_password("clave-secreta")
    segundo_hash = hash_password("clave-secreta")

    assert primer_hash != segundo_hash
    assert primer_hash.startswith("pbkdf2_sha256$")
    assert verify_password("clave-secreta", primer_hash)
    assert not verify_password("otra-clave", primer_hash)
    assert not verify_password("clave-secreta", "formato-invalido")
