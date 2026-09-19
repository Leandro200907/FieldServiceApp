"""Worker: dead-letter explícito en `job_queue`.

`estado = 'fallido'` es el estado terminal (dead-letter): el job no se vuelve a tomar.
Se agregan `ultimo_error` (texto saneado, sin tokens/contraseñas/DSN, <= 500 chars),
`ultimo_error_en` y `fallido_en` para diagnosticar sin leer logs, y un índice parcial
sobre los fallidos para listarlos.

Revision ID: 0015_job_queue_dead_letter
Revises: 0014_readiness_version
"""
from alembic import op

revision = "0015_job_queue_dead_letter"
down_revision = "0014_readiness_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE modulo1.job_queue "
        "ADD COLUMN ultimo_error TEXT, ADD COLUMN ultimo_error_en TIMESTAMPTZ, ADD COLUMN fallido_en TIMESTAMPTZ"
    )
    op.execute("CREATE INDEX ix_job_queue_fallidos ON modulo1.job_queue (cola, fallido_en) WHERE estado = 'fallido'")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.ix_job_queue_fallidos")
    op.execute("ALTER TABLE modulo1.job_queue DROP COLUMN IF EXISTS fallido_en, DROP COLUMN IF EXISTS ultimo_error_en, DROP COLUMN IF EXISTS ultimo_error")
