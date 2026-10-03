"""Restaura NOT NULL en documento.vigente_hasta (semántica única post-0023).

Revision ID: 0025_vigente_hasta_not_null
Revises: 0024_integridad_operativa
"""
from alembic import op

revision = "0025_vigente_hasta_not_null"
down_revision = "0024_integridad_operativa"
branch_labels = None
depends_on = None

_VIGENCIA_ABIERTA = "9999-12-31"


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.documento NO FORCE ROW LEVEL SECURITY")
    op.execute(
        f"UPDATE modulo1.documento SET vigente_hasta = '{_VIGENCIA_ABIERTA}' WHERE vigente_hasta IS NULL"
    )
    op.execute("ALTER TABLE modulo1.documento ALTER COLUMN vigente_hasta SET NOT NULL")
    op.execute("ALTER TABLE modulo1.documento FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.documento NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.documento ALTER COLUMN vigente_hasta DROP NOT NULL")
    op.execute(
        f"UPDATE modulo1.documento SET vigente_hasta = NULL WHERE vigente_hasta = '{_VIGENCIA_ABIERTA}'"
    )
    op.execute("ALTER TABLE modulo1.documento FORCE ROW LEVEL SECURITY")
