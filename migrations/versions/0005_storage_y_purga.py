"""Storage seguro (A-02) y purga en dos fases (A-05): estado del archivo físico en
`documento`.

`archivo_estado`:
  sin_archivo       → el documento no tiene (ni tuvo) archivo adjunto
  subida_pendiente  → `preparar_subida_de_evidencia` derivó la clave y firmó el PUT
  confirmado        → `confirmar_subida_de_evidencia` verificó el archivo real (checksum y
                      bytes calculados en servidor). Único estado descargable.
  purga_pendiente   → el control de retención decidió purgar (fase 1, commiteada)
  purgado           → borrado físico confirmado (fase 2) + evento ArchivoPurgado

La clave la deriva SIEMPRE el servidor (`tenant_id/documento_id/nombre`); ningún body
público la elige. Sin backfill: FORCE RLS impide UPDATE desde la migración y no hay
datos productivos todavía (los tenants de test se limpian).

Revision ID: 0005_storage_y_purga
Revises: 0004_merge
"""
from alembic import op

revision = "0005_storage_y_purga"
down_revision = "0004_merge"
branch_labels = None
depends_on = None

ESTADOS = ("sin_archivo", "subida_pendiente", "confirmado", "purga_pendiente", "purgado")


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE modulo1.documento
            ADD COLUMN archivo_estado TEXT NOT NULL DEFAULT 'sin_archivo'
                CHECK (archivo_estado IN {ESTADOS}),
            ADD COLUMN archivo_content_type TEXT,
            ADD COLUMN archivo_bytes BIGINT CHECK (archivo_bytes IS NULL OR archivo_bytes >= 0),
            ADD COLUMN archivo_purgado_en TIMESTAMPTZ,
            ADD CONSTRAINT ck_archivo_clave_segun_estado CHECK (
                (archivo_estado IN ('sin_archivo', 'purgado') AND clave_storage IS NULL)
                OR (archivo_estado NOT IN ('sin_archivo', 'purgado') AND clave_storage IS NOT NULL)
            ),
            ADD CONSTRAINT ck_archivo_confirmado_con_checksum CHECK (
                archivo_estado <> 'confirmado' OR (checksum_archivo IS NOT NULL AND archivo_bytes IS NOT NULL)
            ),
            ADD CONSTRAINT ck_archivo_clave_del_documento CHECK (
                clave_storage IS NULL
                OR clave_storage LIKE (tenant_id::text || '/' || documento_id::text || '/%')
            )
        """
    )
    op.execute(
        "CREATE INDEX ix_documento_archivo_estado ON modulo1.documento (tenant_id, archivo_estado) "
        "WHERE archivo_estado IN ('subida_pendiente', 'purga_pendiente')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.ix_documento_archivo_estado")
    op.execute(
        """
        ALTER TABLE modulo1.documento
            DROP CONSTRAINT IF EXISTS ck_archivo_clave_del_documento,
            DROP CONSTRAINT IF EXISTS ck_archivo_confirmado_con_checksum,
            DROP CONSTRAINT IF EXISTS ck_archivo_clave_segun_estado,
            DROP COLUMN IF EXISTS archivo_purgado_en,
            DROP COLUMN IF EXISTS archivo_bytes,
            DROP COLUMN IF EXISTS archivo_content_type,
            DROP COLUMN IF EXISTS archivo_estado
        """
    )
