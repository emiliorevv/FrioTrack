"""Pruebas de metadatos del esquema; no crean archivos ni se conectan a una base."""

import pytest
from sqlalchemy import BigInteger, Table, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import dialect as dialecto_postgres
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.db.base import Base

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


def _ddl(tabla: Table) -> str:
    """Compila el CREATE TABLE con el dialecto de Postgres, sin conectarse a nada."""
    return str(CreateTable(tabla).compile(dialect=dialecto_postgres()))


def test_metadata_tiene_las_nueve_tablas():
    assert set(Base.metadata.tables) == TABLAS_ESPERADAS


@pytest.mark.parametrize("nombre", sorted(TABLAS_ESPERADAS))
def test_todas_las_tablas_compilan_para_postgres(nombre: str):
    ddl = _ddl(Base.metadata.tables[nombre])

    assert f"CREATE TABLE {nombre}" in ddl
    assert ddl.strip().endswith(")")


def test_columnas_clave_de_camaras():
    camaras = Base.metadata.tables["camaras"]

    assert {"id", "nombre", "rango_min_c", "rango_max_c", "estado"} <= set(camaras.c.keys())
    assert camaras.c.rango_min_c.type.precision == 4
    assert camaras.c.rango_min_c.type.scale == 1


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
