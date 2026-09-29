"""Lote de importación único por (tenant, lote_id, entidad).

Revision ID: 0026_lote_importacion_por_entidad
Revises: 0025_vigente_hasta_not_null
"""
from alembic import op

revision = "0026_lote_importacion_por_entidad"
down_revision = "0025_vigente_hasta_not_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.lote_importacion NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.documento NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.oc NO FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE modulo1.documento DROP CONSTRAINT IF EXISTS fk_documento__lote_id")
    op.execute("ALTER TABLE modulo1.oc DROP CONSTRAINT IF EXISTS fk_oc__lote_id")
    op.execute("ALTER TABLE modulo1.lote_importacion DROP CONSTRAINT IF EXISTS uq_lote_tenant_id")
    op.execute("ALTER TABLE modulo1.lote_importacion DROP CONSTRAINT lote_importacion_pkey")

    op.execute(
        "ALTER TABLE modulo1.documento ADD COLUMN IF NOT EXISTS lote_entidad text "
        "CHECK (lote_entidad IS NULL OR lote_entidad = 'legajos')"
    )
    op.execute(
        "UPDATE modulo1.documento SET lote_entidad = 'legajos' WHERE lote_id IS NOT NULL AND lote_entidad IS NULL"
    )
    op.execute(
        "ALTER TABLE modulo1.oc ADD COLUMN IF NOT EXISTS lote_entidad text "
        "CHECK (lote_entidad IS NULL OR lote_entidad = 'oc')"
    )
    op.execute(
        "UPDATE modulo1.oc SET lote_entidad = 'oc' WHERE lote_id IS NOT NULL AND lote_entidad IS NULL"
    )

    op.execute(
        "ALTER TABLE modulo1.lote_importacion ADD PRIMARY KEY (tenant_id, lote_id, entidad)"
    )
    op.execute(
        "ALTER TABLE modulo1.documento ADD CONSTRAINT fk_documento__lote_id "
        "FOREIGN KEY (tenant_id, lote_id, lote_entidad) "
        "REFERENCES modulo1.lote_importacion (tenant_id, lote_id, entidad)"
    )
    op.execute(
        "ALTER TABLE modulo1.oc ADD CONSTRAINT fk_oc__lote_id "
        "FOREIGN KEY (tenant_id, lote_id, lote_entidad) "
        "REFERENCES modulo1.lote_importacion (tenant_id, lote_id, entidad)"
    )

    op.execute("ALTER TABLE modulo1.lote_importacion FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.documento FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.oc FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.lote_importacion NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.documento NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.oc NO FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE modulo1.documento DROP CONSTRAINT IF EXISTS fk_documento__lote_id")
    op.execute("ALTER TABLE modulo1.oc DROP CONSTRAINT IF EXISTS fk_oc__lote_id")
    op.execute("ALTER TABLE modulo1.lote_importacion DROP CONSTRAINT lote_importacion_pkey")
    op.execute("ALTER TABLE modulo1.lote_importacion ADD PRIMARY KEY (lote_id)")
    op.execute(
        "ALTER TABLE modulo1.lote_importacion ADD CONSTRAINT uq_lote_tenant_id UNIQUE (tenant_id, lote_id)"
    )
    op.execute(
        "ALTER TABLE modulo1.documento ADD CONSTRAINT fk_documento__lote_id "
        "FOREIGN KEY (tenant_id, lote_id) REFERENCES modulo1.lote_importacion (tenant_id, lote_id)"
    )
    op.execute(
        "ALTER TABLE modulo1.oc ADD CONSTRAINT fk_oc__lote_id "
        "FOREIGN KEY (tenant_id, lote_id) REFERENCES modulo1.lote_importacion (tenant_id, lote_id)"
    )
    op.execute("ALTER TABLE modulo1.documento DROP COLUMN IF EXISTS lote_entidad")
    op.execute("ALTER TABLE modulo1.oc DROP COLUMN IF EXISTS lote_entidad")

    op.execute("ALTER TABLE modulo1.lote_importacion FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.documento FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.oc FORCE ROW LEVEL SECURITY")
