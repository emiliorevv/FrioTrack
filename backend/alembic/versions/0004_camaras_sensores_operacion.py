"""camaras y sensores para operación

- `camaras.es_demo`: solo las cámaras sembradas reciben el tick simulado.
- `sensores.ultima_lectura_en`: caché de la última lectura para listar sin GROUP BY.
- índice `ix_lecturas_sensor_id`: baja de sensores y filtros por sensor.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: str | Sequence[str] | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega el flag de demo, la caché de última lectura y el índice por sensor."""
    op.add_column(
        'camaras',
        sa.Column('es_demo', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Las 5 cámaras del seed original en el tenant demo ya existen; las nuevas
    # nacen con `es_demo=false` desde el default.
    op.execute(
        sa.text(
            'UPDATE camaras SET es_demo = true '
            'WHERE restaurante_id = 1 AND id BETWEEN 1 AND 5'
        )
    )

    op.add_column(
        'sensores',
        sa.Column('ultima_lectura_en', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            'UPDATE sensores SET ultima_lectura_en = ('
            'SELECT max(recibida_en) FROM lecturas '
            'WHERE lecturas.sensor_id = sensores.id'
            ') WHERE ultima_lectura_en IS NULL'
        )
    )

    op.create_index('ix_lecturas_sensor_id', 'lecturas', ['sensor_id'])


def downgrade() -> None:
    """Revierte la caché y el flag; las cámaras siguen siendo las mismas filas."""
    op.drop_index('ix_lecturas_sensor_id', table_name='lecturas')
    op.drop_column('sensores', 'ultima_lectura_en')
    op.drop_column('camaras', 'es_demo')
