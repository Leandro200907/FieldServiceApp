"""Validación técnica de evidencia (reauditoría Fase 2 punto 2): eje independiente
`archivo_validacion` en `documento`, separado de `estado_confirmacion` — igual que
`estado_version` y `estado_confirmacion` ya son ejes independientes entre sí.

- `archivo_validacion` (pendiente/valido/invalido): resultado de la verificación técnica
  del archivo real (formato válido, tipo de contenido coincide con el declarado, PDF no
  corrupto, escaneo de malware si hay uno configurado) — NUNCA de negocio. Nunca mueve
  `estado_confirmacion` por sí sola (esa sigue siendo una decisión humana,
  arquitectura-tecnica.md §8.5).
- `archivo_validacion_motivo` / `archivo_validacion_en`: por qué y cuándo.
- `archivo_validacion_token`: fencing (UUID). Cada ciclo de subida real (confirmar_subida,
  o una invalidación manual) lo regenera; el job de `validacion_evidencia` sólo consolida
  su resultado si el token todavía coincide — un job viejo nunca pisa un archivo
  reemplazado o una invalidación manual posterior.
- `archivo_scan_estado`: honestidad del antivirus — `no_configurado` mientras no haya un
  scanner real conectado (nunca se afirma "limpio" sin haber escaneado de verdad).

Backfill (regla explícita para documentos legacy): todo documento que YA estaba
`archivo_estado = 'confirmado'` antes de esta migración —confirmado sin que existiera
esta validación técnica— queda `archivo_validacion = 'valido'` con motivo explícito, para
no bloquear de golpe la descarga de evidencia ya operativa. Los confirmados DE ACÁ EN
ADELANTE arrancan en `pendiente` y sólo se habilitan para descarga cuando el job los
valide (o alguien los reemplace/invalide a mano).

Revision ID: 0021_validacion_evidencia
Revises: 0020_outbox_backoff_alerta
"""
from alembic import op

revision = "0021_validacion_evidencia"
down_revision = "0020_outbox_backoff_alerta"
branch_labels = None
depends_on = None

_MOTIVO_LEGADO = "legado: confirmado antes de existir la validación técnica (migración 0021)"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE modulo1.documento
            ADD COLUMN archivo_validacion TEXT NOT NULL DEFAULT 'pendiente'
                CHECK (archivo_validacion IN ('pendiente', 'valido', 'invalido')),
            ADD COLUMN archivo_validacion_motivo TEXT,
            ADD COLUMN archivo_validacion_en TIMESTAMPTZ,
            ADD COLUMN archivo_validacion_token UUID,
            ADD COLUMN archivo_scan_estado TEXT
                CHECK (archivo_scan_estado IS NULL OR archivo_scan_estado IN ('no_configurado', 'limpio', 'infectado'))
        """
    )
    op.execute(
        "CREATE INDEX ix_documento_archivo_validacion ON modulo1.documento (tenant_id, archivo_validacion) "
        "WHERE archivo_estado = 'confirmado' AND archivo_validacion <> 'valido'"
    )
    # Backfill cruzando todos los tenants (como en 0016/0019): NO FORCE RLS sólo para esta
    # corrección puntual, restaurado antes de terminar.
    op.execute("ALTER TABLE modulo1.documento NO FORCE ROW LEVEL SECURITY")
    op.execute(
        f"UPDATE modulo1.documento SET archivo_validacion = 'valido', archivo_validacion_motivo = '{_MOTIVO_LEGADO}', "
        f"archivo_validacion_en = now() WHERE archivo_estado = 'confirmado'"
    )
    op.execute("ALTER TABLE modulo1.documento FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.ix_documento_archivo_validacion")
    op.execute(
        """
        ALTER TABLE modulo1.documento
            DROP COLUMN archivo_scan_estado,
            DROP COLUMN archivo_validacion_token,
            DROP COLUMN archivo_validacion_en,
            DROP COLUMN archivo_validacion_motivo,
            DROP COLUMN archivo_validacion
        """
    )
