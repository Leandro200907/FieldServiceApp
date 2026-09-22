"""Índice único (tenant_id, clave_origen) en modulo1.oc.

`clave_origen` es el identificador estable de la OC en el origen (planilla / Drive) y
es lo que hace incremental a ImportarLote (documentacion-habilitante 1.12): una fila
con una clave ya conocida actualiza la OC en vez de duplicarla. El dump 0001 solo tenía
`ix_oc_tenant_estado`, sin unicidad, así que el UPSERT (`ON CONFLICT`) no tenía sobre
qué apoyarse. Solo DDL: no toca datos (FORCE RLS impide UPDATE desde la migración).

Revision ID: 0003_oc_uq_clave_origen
Revises: 0002_usuario_supervisor
"""
from alembic import op

revision = "0003_oc_uq_clave_origen"
down_revision = "0002_usuario_supervisor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_oc_clave_origen ON modulo1.oc (tenant_id, clave_origen)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.uq_oc_clave_origen")
