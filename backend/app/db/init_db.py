"""Crea el esquema y carga los datos semilla.

Uso desde `backend/`:

    python -m app.db.init_db
"""

from sqlalchemy.engine import Engine

from app.db import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.db.base import Base
from app.db.seed import cargar_seed
from app.db.session import SessionLocal, get_engine


def crear_esquema(engine: Engine) -> None:
    """Crea todas las tablas que falten."""
    Base.metadata.create_all(bind=engine)


def inicializar_db() -> bool:
    """Crea el esquema y carga el seed. Regresa False si la base ya tenía datos."""
    engine = get_engine()
    crear_esquema(engine)
    with SessionLocal(bind=engine) as session:
        return cargar_seed(session)


if __name__ == "__main__":
    if inicializar_db():
        print("Esquema listo y datos semilla cargados.")
    else:
        print("La base ya tenía datos; no se cargó nada.")
