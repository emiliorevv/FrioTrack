"""Entrypoint de migración seguro para Render y local.

Uso desde cualquier cwd:

    python -m app.db.migrar

- Base vacía: aplica el baseline.
- Base al día: no ejecuta DDL.
- Base legada de `create_all`, sin `alembic_version`: marca el baseline solo si
  el esquema coincide exactamente; si no, falla sin tocar nada.
- Revisión más nueva que este código (rollback de Render): advierte y no toca
  nada para que la app pueda arrancar.
"""

from __future__ import annotations

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

import app.db.models  # noqa: F401  (registra las 9 tablas en Base.metadata)
from alembic import command
from app.db.base import Base
from app.db.session import crear_engine

RUTA_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
TABLA_NEGOCIO = "camaras"

MENSAJE_DRIFT = (
    "La base no coincide con el baseline de Alembic y no se marcó automáticamente. "
    "Corrige el esquema con una migración nueva; no se aplicó ningún cambio."
)
MENSAJE_REVISION_NUEVA = (
    "La BD está en una revisión más nueva que este deploy ({revision}); "
    "se omite la migración."
)


def config_alembic() -> Config:
    """Config de Alembic con ruta absoluta, independiente del cwd."""
    return Config(str(RUTA_ALEMBIC_INI))


def revision_actual(engine: Engine) -> str | None:
    """Revisión aplicada según `alembic_version` (None si no existe o está vacía)."""
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head(config: Config | None = None) -> str | None:
    """Última revisión disponible en el código."""
    return ScriptDirectory.from_config(config or config_alembic()).get_current_head()


def _revision_en_codigo(config: Config, revision: str) -> bool:
    """Indica si la revisión aplicada existe en este deploy."""
    try:
        return ScriptDirectory.from_config(config).get_revision(revision) is not None
    except CommandError:
        return False


def _marcar_legada(engine: Engine, config: Config, head_actual: str | None) -> None:
    """Marca el baseline en una base con tablas pero sin revisión aplicada."""
    with engine.connect() as conn:
        contexto = MigrationContext.configure(conn, opts={"compare_type": True})
        diferencias = compare_metadata(contexto, Base.metadata)
    if diferencias:
        raise RuntimeError(MENSAJE_DRIFT)
    command.stamp(config, "head")
    print(f"Base legada sin revisión aplicada: se marcó {head_actual}.")


def main() -> None:
    """Migra o marca el baseline según el estado de la base."""
    engine = crear_engine()
    try:
        tablas = set(inspect(engine).get_table_names())
        config = config_alembic()
        head_actual = head(config)

        if "alembic_version" in tablas:
            actual = revision_actual(engine)
            if actual == head_actual:
                print(f"Esquema al día ({head_actual}).")
                return
            if actual is not None:
                if not _revision_en_codigo(config, actual):
                    print(MENSAJE_REVISION_NUEVA.format(revision=actual))
                    return
                command.upgrade(config, "head")
                return
            # `alembic_version` sin fila: con tablas se trata como legada.
            if TABLA_NEGOCIO in tablas:
                _marcar_legada(engine, config, head_actual)
                return
            command.upgrade(config, "head")
            return

        if TABLA_NEGOCIO in tablas:
            _marcar_legada(engine, config, head_actual)
            return

        command.upgrade(config, "head")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
