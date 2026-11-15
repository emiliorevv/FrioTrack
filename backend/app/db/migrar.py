"""Entrypoint de migración seguro para Render y local.

Uso desde cualquier cwd:

    python -m app.db.migrar

- Base vacía: aplica el baseline.
- Base al día: no ejecuta DDL.
- Base legada de `create_all`, sin `alembic_version`: marca el baseline solo si
  el esquema coincide exactamente; si no, falla sin tocar nada.
"""

from __future__ import annotations

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

import app.db.models  # noqa: F401  (registra las 9 tablas en Base.metadata)
from alembic import command
from app.db.base import Base
from app.db.session import crear_engine

RUTA_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

MENSAJE_DRIFT = (
    "La base no coincide con el baseline de Alembic y no se marcó automáticamente. "
    "Corrige el esquema con una migración nueva; no se aplicó ningún cambio."
)


def _config() -> Config:
    """Config de Alembic con ruta absoluta, independiente del cwd."""
    return Config(str(RUTA_ALEMBIC_INI))


def _revision_actual(engine: Engine) -> str | None:
    """Revisión aplicada según la tabla `alembic_version` (None si no existe)."""
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def main() -> None:
    """Migra o marca el baseline según el estado de la base."""
    engine = crear_engine()
    try:
        tablas = set(inspect(engine).get_table_names())
        config = _config()
        head = ScriptDirectory.from_config(config).get_current_head()

        if "alembic_version" in tablas:
            actual = _revision_actual(engine)
            if actual == head:
                print(f"Esquema al día ({head}).")
                return
            command.upgrade(config, "head")
            return

        if "camaras" in tablas:
            # Base legada creada con create_all: solo se marca si coincide.
            with engine.connect() as conn:
                contexto = MigrationContext.configure(conn, opts={"compare_type": True})
                diferencias = compare_metadata(contexto, Base.metadata)
            if diferencias:
                raise RuntimeError(MENSAJE_DRIFT)
            command.stamp(config, "head")
            print(f"Base legada sin alembic_version: se marcó {head}.")
            return

        command.upgrade(config, "head")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
