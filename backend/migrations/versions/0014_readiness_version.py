"""Readiness: el rol de aplicación puede leer `alembic_version` (sólo SELECT) para
comparar la migración aplicada con el head que el código espera (`app.version`).

Revision ID: 0014_readiness_version
Revises: 0013_definicion_unicidad_null
"""
from alembic import op

revision = "0014_readiness_version"
down_revision = "0013_definicion_unicidad_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON TABLE public.alembic_version TO modulo1_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON TABLE public.alembic_version FROM modulo1_app")
