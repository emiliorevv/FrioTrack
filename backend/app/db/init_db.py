"""Verifica la revisión de Alembic y carga los datos semilla.

El esquema lo administran las migraciones; este módulo no migra ni crea tablas.
Uso desde cualquier cwd:

    python -m app.db.migrar
    python -m app.db.init_db
"""

from sqlalchemy.engine import Engine

from app.db.migrar import config_alembic, head, revision_actual
from app.db.seed import cargar_seed
from app.db.session import SessionLocal, get_engine

MENSAJE_FALTA_ESQUEMA = (
    "Falta el esquema o está desactualizado: ejecuta `python -m app.db.migrar` "
    "(o `alembic upgrade head`)."
)


def esquema_actualizado(engine: Engine) -> bool:
    """Indica si la base está en la última revisión de Alembic."""
    config = config_alembic()
    return revision_actual(engine) == head(config)


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
