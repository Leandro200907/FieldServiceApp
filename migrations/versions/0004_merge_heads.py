"""Merge de los cuatro heads 0003 (auth, legajos, oc, worker) creados en paralelo.

Revision ID: 0004_merge
Revises: 0003_auth_resolver_tenant, 0003_legajos_sucede_a, 0003_oc_uq_clave_origen, 0003_worker_latido
"""

revision = "0004_merge"
down_revision = ("0003_auth_resolver_tenant", "0003_legajos_sucede_a", "0003_oc_uq_clave_origen", "0003_worker_latido")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
