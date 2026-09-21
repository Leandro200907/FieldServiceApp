"""Outbox con backoff, estado estancado y alerta obligatoria (reauditoría Fase 2 punto 5).

`drenaje_outbox` es la cola crítica ("una falla persistente acá significa que Módulo 2
nunca se entera de un cambio de cumplimiento", arquitectura-tecnica.md §8.4) y la
especificación exige explícitamente: más reintentos/mayor duración que las demás colas, y
una alerta obligatoria al agotarse — **nunca dead-letter silencioso**. El drenaje real no
tenía ninguna de las tres cosas: reintentaba cada vuelta del worker sin backoff, sin tope
de intentos (un evento envenenado se reintentaba para siempre) y sin ningún mecanismo de
alerta.

Columnas nuevas en `outbox_events`:
- `disponible_en`: igual que `job_queue`, no se reintenta antes de que venza el backoff.
- `ultimo_error`: error saneado del último intento fallido (ver `sanear_error`).
- `estancado_en`: NULL mientras sigue reintentando; se fija cuando agota el tope de
  intentos — a partir de ahí `drenar_outbox` ya no lo vuelve a tomar (así se evita el
  martilleo eterno), pero la fila NUNCA se borra ni queda oculta: sigue siendo consultable
  y reprocesable a mano (`scripts/administracion.py reprocesar-outbox`).

Revision ID: 0020_outbox_backoff_alerta
Revises: 0019_notificacion_sin_canal
"""
from alembic import op

revision = "0020_outbox_backoff_alerta"
down_revision = "0019_notificacion_sin_canal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.outbox_events ADD COLUMN disponible_en TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute("ALTER TABLE modulo1.outbox_events ADD COLUMN ultimo_error TEXT")
    op.execute("ALTER TABLE modulo1.outbox_events ADD COLUMN estancado_en TIMESTAMPTZ")
    op.execute("CREATE INDEX ix_outbox_disponibles ON modulo1.outbox_events (tenant_id, disponible_en) "
               "WHERE procesado_en IS NULL AND estancado_en IS NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.ix_outbox_disponibles")
    op.execute("ALTER TABLE modulo1.outbox_events DROP COLUMN estancado_en")
    op.execute("ALTER TABLE modulo1.outbox_events DROP COLUMN ultimo_error")
    op.execute("ALTER TABLE modulo1.outbox_events DROP COLUMN disponible_en")
