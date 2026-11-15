"""Verifica la revisión de Alembic y carga los datos semilla.

El esquema lo administran las migraciones; este módulo no migra ni crea tablas.
Uso desde cualquier cwd:

    python -m app.db.migrar
    python -m app.db.init_db
"""

from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

from app.db.seed import cargar_seed
from app.db.session import SessionLocal, get_engine

RUTA_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

MENSAJE_FALTA_ESQUEMA = (
    "Falta el esquema o está desactualizado: ejecuta `python -m app.db.migrar` "
    "(o `alembic upgrade head`)."
)


def esquema_actualizado(engine: Engine) -> bool:
    """Indica si la base está en la última revisión de Alembic."""
    config = Config(str(RUTA_ALEMBIC_INI))
    head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as conn:
        actual = MigrationContext.configure(conn).get_current_revision()
    return actual == head


def inicializar_db() -> bool:
    """Carga el seed sobre un esquema migrado. Regresa False si ya había datos."""
    engine = get_engine()
    if not esquema_actualizado(engine):
        raise RuntimeError(MENSAJE_FALTA_ESQUEMA)
    with SessionLocal(bind=engine) as session:
        return cargar_seed(session)


if __name__ == "__main__":
    try:
        if inicializar_db():
            print("Datos semilla cargados.")
        else:
            print("La base ya tenía datos; no se cargó nada.")
    except RuntimeError as error:
        raise SystemExit(f"Error: {error}") from error
