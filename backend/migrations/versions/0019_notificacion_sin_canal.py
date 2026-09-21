"""Notificaciones sin pérdida silenciosa (reauditoría, Fase 2 punto 1).

`notificacion_envio` ganaba, hasta acá, solo dos estados (`enviado` / `fallido`) y un
canal `log` que se contaba como `enviado` igual que un envío real por mail/Telegram. Dos
problemas reales: (a) un destinatario sin email ni Telegram vinculado, mezclado con otros
que sí tenían canal, se caía del plan de envío sin ninguna fila de traza — desaparecía sin
rastro; (b) cuando NINGÚN canal está habilitado para el tenant, el mensaje se registra en
el log del proceso y queda contado exactamente igual que un envío real, sin forma de
distinguir "entregado de verdad" de "solo quedó en el log" desde una consulta.

- `sin_canal` en `canal` y `estado`: fila por destinatario sin canal resoluble para él (el
  tenant sí tiene algún canal habilitado, a esa persona en particular le falta el dato de
  contacto). `destinatario` = `usuario_id` (no hay destino real al que apuntar).
- `registrado_log` en `estado`: lo que antes se guardaba como `enviado` con `canal='log'`
  pasa a un estado propio, para que ninguna consulta lo confunda con una entrega real.

Revision ID: 0019_notificacion_sin_canal
Revises: 0018_capacidades_v1
"""
from alembic import op

revision = "0019_notificacion_sin_canal"
down_revision = "0018_capacidades_v1"
branch_labels = None
depends_on = None

_CANAL_VIEJO = "notificacion_envio_canal_check"
_ESTADO_VIEJO = "notificacion_envio_estado_check"


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.notificacion_envio DROP CONSTRAINT " + _CANAL_VIEJO)
    op.execute("ALTER TABLE modulo1.notificacion_envio ADD CONSTRAINT " + _CANAL_VIEJO +
               " CHECK (canal IN ('mail', 'telegram', 'log', 'sin_canal'))")
    op.execute("ALTER TABLE modulo1.notificacion_envio DROP CONSTRAINT " + _ESTADO_VIEJO)
    op.execute("ALTER TABLE modulo1.notificacion_envio ADD CONSTRAINT " + _ESTADO_VIEJO +
               " CHECK (estado IN ('enviado', 'fallido', 'sin_canal', 'registrado_log'))")
    # Backfill cruzando todos los tenants (como en 0016 §copiada_de_version): NO FORCE RLS
    # sólo para esta corrección puntual, restaurado antes de terminar.
    op.execute("ALTER TABLE modulo1.notificacion_envio NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE modulo1.notificacion_envio SET estado = 'registrado_log' WHERE canal = 'log' AND estado = 'enviado'")
    op.execute("ALTER TABLE modulo1.notificacion_envio FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.notificacion_envio NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE modulo1.notificacion_envio SET estado = 'enviado' WHERE canal = 'log' AND estado = 'registrado_log'")
    op.execute("DELETE FROM modulo1.notificacion_envio WHERE canal = 'sin_canal' OR estado = 'sin_canal'")
    op.execute("ALTER TABLE modulo1.notificacion_envio FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.notificacion_envio DROP CONSTRAINT " + _ESTADO_VIEJO)
    op.execute("ALTER TABLE modulo1.notificacion_envio ADD CONSTRAINT " + _ESTADO_VIEJO +
               " CHECK (estado IN ('enviado', 'fallido'))")
    op.execute("ALTER TABLE modulo1.notificacion_envio DROP CONSTRAINT " + _CANAL_VIEJO)
    op.execute("ALTER TABLE modulo1.notificacion_envio ADD CONSTRAINT " + _CANAL_VIEJO +
               " CHECK (canal IN ('mail', 'telegram', 'log'))")
