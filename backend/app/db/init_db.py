"""Verifica el esquema y carga los datos semilla.

El esquema lo crean las migraciones de Alembic; este módulo ya no llama a
`create_all`. Uso desde `backend/`:

    alembic upgrade head
    python -m app.db.init_db
"""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.db.seed import cargar_seed
from app.db.session import SessionLocal, get_engine

MENSAJE_FALTA_ESQUEMA = (
    "Falta el esquema: ejecuta `alembic upgrade head` antes de cargar el seed."
)


def esquema_existe(engine: Engine) -> bool:
    """Indica si la tabla `camaras` ya existe (la crea el baseline de Alembic)."""
    return inspect(engine).has_table("camaras")


def inicializar_db() -> bool:
    """Carga el seed sobre un esquema migrado. Regresa False si ya había datos."""
    engine = get_engine()
    if not esquema_existe(engine):
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
