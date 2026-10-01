"""Nombre de operadora documental no puede quedar vacío.

Revision ID: 0027_operadora_nombre
Revises: 0026_lote_por_entidad
"""
from alembic import op

revision = "0027_operadora_nombre"
down_revision = "0026_lote_por_entidad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.operadora_documental NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM modulo1.operadora_documental WHERE btrim(nombre) = ''")
    op.execute(
        "ALTER TABLE modulo1.operadora_documental "
        "ADD CONSTRAINT ck_operadora_documental_nombre "
        "CHECK (btrim(nombre) <> '')"
    )
    op.execute("ALTER TABLE modulo1.operadora_documental FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.operadora_documental NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE modulo1.operadora_documental "
        "DROP CONSTRAINT IF EXISTS ck_operadora_documental_nombre"
    )
    op.execute("ALTER TABLE modulo1.operadora_documental FORCE ROW LEVEL SECURITY")
