"""Pruebas de la lógica de decisión de app.db.migrar."""

from types import SimpleNamespace

import pytest

from app.db import migrar


class _ConexionFalsa:
    def __enter__(self):
        return object()

    def __exit__(self, *args):
        return False


class _EngineFalso:
    def __init__(self):
        self.descartado = False

    def connect(self):
        return _ConexionFalsa()

    def dispose(self):
        self.descartado = True


def _correr(
    monkeypatch,
    *,
    tablas: set[str],
    actual: str | None = None,
    head: str = "0001",
    conocida: bool = True,
    diferencias: list | None = None,
):
    engine = _EngineFalso()
    llamadas: dict[str, list[str]] = {"upgrade": [], "stamp": []}
    monkeypatch.setattr(migrar, "crear_engine", lambda: engine)
    monkeypatch.setattr(
        migrar,
        "inspect",
        lambda _engine: SimpleNamespace(get_table_names=lambda: sorted(tablas)),
    )
    monkeypatch.setattr(migrar, "config_alembic", lambda: "config")
    monkeypatch.setattr(migrar, "head", lambda config=None: head)
    monkeypatch.setattr(migrar, "revision_actual", lambda _engine: actual)
    monkeypatch.setattr(migrar, "_revision_en_codigo", lambda config, revision: conocida)
    monkeypatch.setattr(
        migrar, "MigrationContext", SimpleNamespace(configure=lambda *a, **k: object())
    )
    monkeypatch.setattr(
        migrar,
        "compare_metadata",
        lambda contexto, metadata: list(diferencias or []),
    )
    monkeypatch.setattr(
        migrar,
        "command",
        SimpleNamespace(
            upgrade=lambda config, destino: llamadas["upgrade"].append(destino),
            stamp=lambda config, destino: llamadas["stamp"].append(destino),
        ),
    )
    migrar.main()
    return engine, llamadas


def test_base_vacia_aplica_el_baseline(monkeypatch):
    engine, llamadas = _correr(monkeypatch, tablas=set())

    assert llamadas == {"upgrade": ["head"], "stamp": []}
    assert engine.descartado is True


def test_base_al_dia_no_ejecuta_ddl(monkeypatch, capsys):
    _, llamadas = _correr(monkeypatch, tablas={"alembic_version"}, actual="0001")

    assert llamadas == {"upgrade": [], "stamp": []}
    assert "Esquema al día" in capsys.readouterr().out


def test_revision_atras_aplica_upgrade(monkeypatch):
    _, llamadas = _correr(
        monkeypatch, tablas={"alembic_version"}, actual="0000", conocida=True
    )

    assert llamadas == {"upgrade": ["head"], "stamp": []}


def test_revision_desconocida_avisa_y_no_toca_nada(monkeypatch, capsys):
    _, llamadas = _correr(
        monkeypatch, tablas={"alembic_version"}, actual="0002", conocida=False
    )

    assert llamadas == {"upgrade": [], "stamp": []}
    salida = capsys.readouterr().out
    assert "revisión más nueva" in salida
    assert "0002" in salida


def test_legada_sin_alembic_version_marca(monkeypatch, capsys):
    _, llamadas = _correr(monkeypatch, tablas={"camaras", "lotes"})

    assert llamadas == {"upgrade": [], "stamp": ["head"]}
    assert "Base legada" in capsys.readouterr().out


def test_version_vacia_con_tablas_usa_ruta_legada(monkeypatch):
    _, llamadas = _correr(
        monkeypatch, tablas={"alembic_version", "camaras"}, actual=None
    )

    assert llamadas == {"upgrade": [], "stamp": ["head"]}


def test_version_vacia_sin_tablas_aplica_upgrade(monkeypatch):
    _, llamadas = _correr(monkeypatch, tablas={"alembic_version"}, actual=None)

    assert llamadas == {"upgrade": ["head"], "stamp": []}


def test_legada_con_drift_falla_sin_marcar(monkeypatch):
    with pytest.raises(RuntimeError, match="no coincide"):
        _correr(
            monkeypatch,
            tablas={"camaras"},
            diferencias=[("add_column", object())],
        )


def test_revision_en_codigo_detecta_revisiones_desconocidas():
    """`get_revision` lanza CommandError si el id no existe; el helper lo trata como False."""
    config = migrar.config_alembic()

    assert migrar._revision_en_codigo(config, "0001") is True
    assert migrar._revision_en_codigo(config, "9999") is False
