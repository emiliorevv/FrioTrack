"""Entorno de Alembic: conecta las migraciones con los modelos de FríoTrack.

La URL sale de `app.config.get_settings().database_url`, nunca del `alembic.ini`,
para no guardar credenciales en el repo. Funciona desde `backend/` y desde la
raíz con `alembic -c backend/alembic.ini`.
"""

from __future__ import annotations

from typing import Any

import app.db.models  # noqa: F401  (registra las 9 tablas en Base.metadata)
from alembic import context
from app.config import get_settings
from app.db.base import Base
from app.db.session import crear_engine

config = context.config
target_metadata = Base.metadata


def _opciones() -> dict[str, Any]:
    """Opciones comunes de conexión y autogenerate."""
    return {
        "target_metadata": target_metadata,
        # Detecta cambios de tipo en las columnas.
        "compare_type": True,
        # Sin compare_server_default: los defaults viven en Python y compararlos
        # contra Postgres generaría ruido en cada autogenerate.
    }


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse a la base (`alembic upgrade --sql`)."""
    context.configure(
        url=get_settings().database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_opciones(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra la base configurada."""
    # Mismo engine que la API: conserva connect_timeout y la validación de URL.
    engine = crear_engine()
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, **_opciones())
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
