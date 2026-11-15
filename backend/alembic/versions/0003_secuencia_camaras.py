"""alinea la secuencia de camaras

El seed inserta las cámaras 1 a 5 con id explícito y deja `camaras_id_seq` en 1;
el primer alta por API pedía `nextval=1` y chocaba con la PK. Esta revisión deja
la secuencia en MAX(id) para las bases que ya estaban sembradas.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Con la tabla vacía, `is_called=false` deja el próximo nextval en 1; con filas,
# la secuencia queda en MAX(id) y el próximo alta recibe MAX(id) + 1.
SQL_ALINEAR_SECUENCIA = (
    "SELECT setval(pg_get_serial_sequence('camaras', 'id'), "
    "COALESCE((SELECT MAX(id) FROM camaras), 1), "
    "(SELECT MAX(id) FROM camaras) IS NOT NULL)"
)


def upgrade() -> None:
    """Alinea la secuencia con los ids ya insertados por el seed."""
    op.execute(sa.text(SQL_ALINEAR_SECUENCIA))


def downgrade() -> None:
    """No hay nada que revertir: la secuencia sigue siendo válida."""
