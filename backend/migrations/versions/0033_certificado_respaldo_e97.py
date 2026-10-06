"""E-97: certificado propio para respaldo de inducción/competencia.

Revision ID: 0033_certificado_respaldo_e97
Revises: 0032_horizonte_backlog_dias
"""
from alembic import op

revision = "0033_certificado_respaldo_e97"
down_revision = "0032_horizonte_backlog_dias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.documento_soporte
        ADD COLUMN es_certificado_propio BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute("ALTER TABLE modulo1.documento DROP CONSTRAINT IF EXISTS documento_origen_check")
    op.execute(
        """
        ALTER TABLE modulo1.documento ADD CONSTRAINT documento_origen_check
        CHECK (origen = ANY (ARRAY[
            'planilla'::text, 'carga_manual'::text, 'drive'::text, 'certificado_respaldo'::text
        ]))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.documento DROP CONSTRAINT IF EXISTS documento_origen_check")
    op.execute(
        """
        ALTER TABLE modulo1.documento ADD CONSTRAINT documento_origen_check
        CHECK (origen = ANY (ARRAY['planilla'::text, 'carga_manual'::text, 'drive'::text]))
        """
    )
    op.execute("ALTER TABLE modulo1.documento_soporte DROP COLUMN IF EXISTS es_certificado_propio")
