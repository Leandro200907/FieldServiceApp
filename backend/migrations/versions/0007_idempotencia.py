"""A-03: idempotencia con reserva atómica ANTES del efecto.

`idempotency_keys` pasa a ser una reserva con ciclo de vida:
  en_proceso  → reservada en su propia transacción (commiteada) antes de ejecutar el
                efecto; visible para cualquier solicitud concurrente con la misma clave.
  completada  → efecto commiteado + resultado guardado (misma transacción que el efecto).
`fingerprint` (SHA-256 de método + ruta + body) evita reutilizar una clave con otro
request. `reservada_hasta` permite recuperar una reserva huérfana (proceso caído entre
la reserva y el efecto) sin esperar las 24 h de `expira_en`.

Revision ID: 0007_idempotencia
Revises: 0006_evaluacion_sujetos
"""
from alembic import op

revision = "0007_idempotencia"
down_revision = "0006_evaluacion_sujetos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.idempotency_keys
            ADD COLUMN estado TEXT NOT NULL DEFAULT 'completada'
                CONSTRAINT ck_idem_estado CHECK (estado IN ('en_proceso', 'completada')),
            ADD COLUMN fingerprint TEXT,
            ADD COLUMN reservada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            ADD COLUMN reservada_hasta TIMESTAMPTZ NOT NULL DEFAULT now() + interval '2 minutes',
            ADD CONSTRAINT ck_idem_resultado_segun_estado CHECK (
                (estado = 'completada' AND resultado IS NOT NULL) OR (estado = 'en_proceso' AND resultado IS NULL)
            )
        """
    )
    op.execute("ALTER TABLE modulo1.idempotency_keys ALTER COLUMN estado DROP DEFAULT")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.idempotency_keys
            DROP CONSTRAINT IF EXISTS ck_idem_resultado_segun_estado,
            DROP COLUMN IF EXISTS reservada_hasta,
            DROP COLUMN IF EXISTS reservada_en,
            DROP COLUMN IF EXISTS fingerprint,
            DROP COLUMN IF EXISTS estado
        """
    )
