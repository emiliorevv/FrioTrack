"""restaurantes y tenant por restaurante

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-14 23:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Solo se guarda el tenant donde es la fuente de verdad: usuarios y cámaras.
# `lotes` y `alertas` lo derivan de su cámara, y `lecturas`/`sensores` también.
TABLAS_CON_TENANT = ('usuarios', 'camaras')

SQL_SECUENCIA_RESTAURANTES = (
    "SELECT setval(pg_get_serial_sequence('restaurantes', 'id'), "
    "(SELECT MAX(id) FROM restaurantes))"
)


def upgrade() -> None:
    """Crea `restaurantes` y aísla los datos existentes en el restaurante demo."""
    op.create_table(
        'restaurantes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # El restaurante 1 es la demo actual; el seed lo reutiliza en vez de duplicarlo.
    op.execute(
        sa.text(
            "INSERT INTO restaurantes (id, nombre, creado_en) "
            "VALUES (1, 'FríoTrack Demo', now())"
        )
    )
    # El id fue explícito: sin esto, el primer alta sin id chocaría con la PK.
    op.execute(sa.text(SQL_SECUENCIA_RESTAURANTES))

    for tabla in TABLAS_CON_TENANT:
        op.add_column(tabla, sa.Column('restaurante_id', sa.Integer(), nullable=True))
        # Toda fila existente (la demo de Supabase incluida) pasa al tenant 1.
        op.execute(sa.text(f'UPDATE {tabla} SET restaurante_id = 1'))
        op.alter_column(tabla, 'restaurante_id', nullable=False)
        op.create_foreign_key(
            f'fk_{tabla}_restaurante_id',
            tabla,
            'restaurantes',
            ['restaurante_id'],
            ['id'],
        )
        op.create_index(f'ix_{tabla}_restaurante_id', tabla, ['restaurante_id'])


def downgrade() -> None:
    """Quita el tenant; las filas y el resto de sus datos quedan intactos."""
    for tabla in reversed(TABLAS_CON_TENANT):
        op.drop_index(f'ix_{tabla}_restaurante_id', table_name=tabla)
        op.drop_constraint(f'fk_{tabla}_restaurante_id', tabla, type_='foreignkey')
        op.drop_column(tabla, 'restaurante_id')
    op.drop_table('restaurantes')
