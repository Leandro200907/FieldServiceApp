"""Nombre y apellido en legajo de persona (D14).

Revision ID: 0030_legajo_nombre_apellido
Revises: 0029_mov_operadora
"""
from alembic import op

revision = "0030_legajo_nombre_apellido"
down_revision = "0029_mov_operadora"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.legajo
        ADD COLUMN nombre_apellido TEXT
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.legajo DROP COLUMN IF EXISTS nombre_apellido")
