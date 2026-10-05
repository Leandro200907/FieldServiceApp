"""E-91: horizonte del backlog documental configurable por tenant (default 60 días, D23).

Revision ID: 0032_horizonte_backlog_dias
Revises: 0031_documento_estado_propuesta
"""
from alembic import op

revision = "0032_horizonte_backlog_dias"
down_revision = "0031_documento_estado_propuesta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.configuracion_alertas
        ADD COLUMN horizonte_backlog_dias INTEGER NOT NULL DEFAULT 60
            CHECK (horizonte_backlog_dias BETWEEN 1 AND 366)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.configuracion_alertas DROP COLUMN IF EXISTS horizonte_backlog_dias")
