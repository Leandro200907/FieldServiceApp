"""A-06: leases de `job_queue` con propietario.

`lease_token` es un UUID nuevo en cada adquisición (`tomar`). Completar, fallar y renovar
exigen `WHERE estado='en_curso' AND lease_token = :token` y verifican que se afectó
exactamente una fila: un worker cuyo lease venció y fue readquirido por otro ya no
puede tocar la tarea. El token se limpia al salir de `en_curso`.

Revision ID: 0008_worker_leases
Revises: 0007_idempotencia
"""
from alembic import op

revision = "0008_worker_leases"
down_revision = "0007_idempotencia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.job_queue
            ADD COLUMN lease_token UUID,
            ADD CONSTRAINT ck_job_lease_token_segun_estado CHECK (
                (estado = 'en_curso' AND lease_token IS NOT NULL AND lease_hasta IS NOT NULL)
                OR (estado <> 'en_curso' AND lease_token IS NULL)
            )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE modulo1.job_queue DROP CONSTRAINT IF EXISTS ck_job_lease_token_segun_estado, "
        "DROP COLUMN IF EXISTS lease_token"
    )
