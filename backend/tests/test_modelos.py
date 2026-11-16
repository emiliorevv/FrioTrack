"""Pruebas de metadatos del esquema; no crean archivos ni se conectan a una base."""

import pytest
from sqlalchemy import BigInteger, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import dialect as dialecto_postgres
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.db.base import Base

TABLAS_ESPERADAS = {
    "restaurantes",
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


def _ddl(tabla: Table) -> str:
    """Compila el CREATE TABLE con el dialecto de Postgres, sin conectarse a nada."""
    return str(CreateTable(tabla).compile(dialect=dialecto_postgres()))


def test_metadata_tiene_las_diez_tablas():
    assert set(Base.metadata.tables) == TABLAS_ESPERADAS


@pytest.mark.parametrize("nombre", sorted(TABLAS_ESPERADAS))
def test_todas_las_tablas_compilan_para_postgres(nombre: str):
    ddl = _ddl(Base.metadata.tables[nombre])

    assert f"CREATE TABLE {nombre}" in ddl
    assert ddl.strip().endswith(")")


def test_columnas_clave_de_camaras():
    camaras = Base.metadata.tables["camaras"]

    assert {"id", "nombre", "es_demo", "rango_min_c", "rango_max_c", "estado"} <= set(
        camaras.c.keys()
    )
    assert camaras.c.es_demo.default.arg is False
    assert camaras.c.rango_min_c.type.precision == 4
    assert camaras.c.rango_min_c.type.scale == 1


def test_sensores_cachean_la_ultima_lectura():
    sensores = Base.metadata.tables["sensores"]

    assert "ultima_lectura_en" in sensores.c
    assert "ultima_lectura_en TIMESTAMP WITH TIME ZONE" in _ddl(sensores)


def test_lecturas_tiene_indice_por_sensor():
    indices = {
        indice.name: [columna.name for columna in indice.columns]
        for indice in Base.metadata.tables["lecturas"].indexes
    }

    assert indices["ix_lecturas_sensor_id"] == ["sensor_id"]


def test_columnas_clave_de_lecturas():
    lecturas = Base.metadata.tables["lecturas"]

    assert {"id", "camara_id", "sensor_id", "ts", "recibida_en", "temperatura_c"} <= set(
        lecturas.c.keys()
    )
    assert "recibida_en TIMESTAMP WITH TIME ZONE" in _ddl(lecturas)


@pytest.mark.parametrize("nombre", ["lecturas", "logs_acceso"])
def test_pks_grandes_son_bigserial(nombre: str):
    columna = Base.metadata.tables[nombre].c.id

    assert isinstance(columna.type, BigInteger)
    assert "BIGSERIAL" in _ddl(Base.metadata.tables[nombre])


def test_detalle_de_alertas_seguridad_es_jsonb():
    tabla = Base.metadata.tables["alertas_seguridad"]

    assert isinstance(tabla.c.detalle.type, JSONB)
    assert "detalle JSONB" in _ddl(tabla)


def test_indice_unico_parcial_de_alertas_esta_en_metadata():
    indices = [
        indice
        for indice in Base.metadata.tables["alertas"].indexes
        if indice.name == "uq_alertas_abierta_camara_tipo"
    ]

    assert len(indices) == 1
    indice = indices[0]
    assert indice.unique is True
    assert [columna.name for columna in indice.columns] == ["camara_id", "tipo"]
    where = indice.dialect_options["postgresql"]["where"]
    assert str(where) == "cerrada_en IS NULL"

    ddl = str(CreateIndex(indice).compile(dialect=dialecto_postgres()))
    assert "CREATE UNIQUE INDEX" in ddl
    assert "cerrada_en IS NULL" in ddl


def test_alerta_nace_sin_sms_enviados():
    columna = Base.metadata.tables["alertas"].c.sms_enviados

    assert columna.default.arg == 0


def test_aristas_sin_fk_documentadas():
    camaras = Base.metadata.tables["camaras"]
    lecturas = Base.metadata.tables["lecturas"]
    sensores = Base.metadata.tables["sensores"]

    # camaras.ultima_lectura_id y lecturas.sensor_id no llevan FK a propósito.
    assert camaras.c.ultima_lectura_id.foreign_keys == set()
    assert lecturas.c.sensor_id.foreign_keys == set()
    assert isinstance(lecturas.c.sensor_id.type, Text)

    # El resto de las relaciones sí son FK reales.
    assert {fk.target_fullname for fk in lecturas.c.camara_id.foreign_keys} == {"camaras.id"}
    assert {fk.target_fullname for fk in sensores.c.camara_id.foreign_keys} == {"camaras.id"}


def test_restaurantes_es_la_raiz_del_tenant():
    tabla = Base.metadata.tables["restaurantes"]

    assert {"id", "nombre", "creado_en"} == set(tabla.c.keys())
    assert tabla.c.creado_en.default.arg.__name__ == "utcnow"


@pytest.mark.parametrize("nombre", ["usuarios", "camaras"])
def test_tablas_con_tenant_llevan_restaurante_id_con_indice(nombre: str):
    tabla = Base.metadata.tables[nombre]

    assert {fk.target_fullname for fk in tabla.c.restaurante_id.foreign_keys} == {
        "restaurantes.id"
    }
    assert tabla.c.restaurante_id.nullable is False
    indices = {
        indice.name: [columna.name for columna in indice.columns]
        for indice in tabla.indexes
    }
    assert indices[f"ix_{nombre}_restaurante_id"] == ["restaurante_id"]


@pytest.mark.parametrize("nombre", ["lecturas", "sensores", "lotes", "alertas"])
def test_el_resto_deriva_el_tenant_de_la_camara(nombre: str):
    assert "restaurante_id" not in Base.metadata.tables[nombre].c
