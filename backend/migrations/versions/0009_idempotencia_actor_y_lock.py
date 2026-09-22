"""A-03 (corrección): idempotencia con ámbito por actor y exclusión real durante el efecto.

- PK pasa a (tenant_id, actor_id, idempotency_key): una respuesta idempotente solo la
  reproduce quien la generó; otro usuario del tenant entra por su propio ámbito y vuelve a
  pasar por autorización y alcance.
- `reservation_token`: propietario de la reserva; toda consolidación exige
  `estado='en_proceso' AND reservation_token = :token`.
- La exclusión durante el efecto la da `SELECT … FOR UPDATE NOWAIT` sobre esta fila,
  sostenido hasta el commit del efecto (ver app/comun/idempotencia.py). `reservada_hasta`
  queda como dato informativo: la recuperación de una reserva huérfana solo ocurre cuando
  el lock está libre (nadie ejecutando) y con el MISMO fingerprint.

Revision ID: 0009_idempotencia_actor
Revises: 0008_worker_leases
"""
from alembic import op

revision = "0009_idempotencia_actor"
down_revision = "0008_worker_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.idempotency_keys DROP CONSTRAINT idempotency_keys_pkey")
    op.execute(
        """
        ALTER TABLE modulo1.idempotency_keys
            ADD COLUMN actor_id TEXT NOT NULL DEFAULT '',
            ADD COLUMN reservation_token UUID,
            ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (tenant_id, actor_id, idempotency_key),
            ADD CONSTRAINT ck_idem_fingerprint_obligatorio CHECK (fingerprint IS NOT NULL),
            ADD CONSTRAINT ck_idem_token_segun_estado CHECK (
                (estado = 'en_proceso' AND reservation_token IS NOT NULL) OR estado = 'completada'
            )
        """
    )
    op.execute("ALTER TABLE modulo1.idempotency_keys ALTER COLUMN actor_id DROP DEFAULT")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.idempotency_keys
            DROP CONSTRAINT IF EXISTS ck_idem_token_segun_estado,
            DROP CONSTRAINT IF EXISTS ck_idem_fingerprint_obligatorio,
            DROP CONSTRAINT idempotency_keys_pkey,
            DROP COLUMN IF EXISTS reservation_token,
            DROP COLUMN IF EXISTS actor_id,
            ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (tenant_id, idempotency_key)
        """
    )
