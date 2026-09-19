"""M-04: unicidad NULL-aware de la definición de requisito.

Clave de negocio completa de `definicion_requisito`:
    (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id)
`locacion_id` es NULL para todo lo que no es inducción; con el UNIQUE clásico dos
definiciones iguales con locación NULL NO chocaban (NULL <> NULL). Se reemplaza por
`UNIQUE NULLS NOT DISTINCT` (PostgreSQL ≥ 15) sobre la misma clave. Aplica a todas las
filas (activas y dadas de baja): el servicio ya trataba una definición repetida como 409
sin importar `activa`, y así una baja no "libera" el nombre para una duplicada.

Antes de cambiar la restricción se buscan duplicados NULL-aware; si hay, aborta con
diagnóstico y no toca datos.

Revision ID: 0013_definicion_unicidad_null
Revises: 0012_unicidad_operacion_activa
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_definicion_unicidad_null"
down_revision = "0012_unicidad_operacion_activa"
branch_labels = None
depends_on = None

CLAVE = "tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id"
NUEVA = "uq_definicion_clave_negocio"
VIEJA = "uq_definicion_requisito"

# GROUP BY trata los NULL como iguales: detecta también los duplicados con locacion_id NULL.
SQL_DUPLICADOS = (
    f"SELECT {CLAVE}, count(*) AS n FROM modulo1.definicion_requisito "
    f"GROUP BY {CLAVE} HAVING count(*) > 1"
)


def _sin_force(fn):
    op.execute("ALTER TABLE modulo1.definicion_requisito NO FORCE ROW LEVEL SECURITY")
    try:
        fn()
    finally:
        op.execute("ALTER TABLE modulo1.definicion_requisito FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    def _hacer():
        filas = op.get_bind().execute(sa.text(SQL_DUPLICADOS)).all()
        if filas:
            raise RuntimeError(
                f"0013 abortada: {len(filas)} clave(s) de definición duplicada(s) (NULL-aware); resolver a mano antes de "
                f"migrar. Ejemplo (tenant, nombre, categoria, tipo_sujeto, locacion, n): {tuple(filas[0])}"
            )
        op.execute(f"ALTER TABLE modulo1.definicion_requisito DROP CONSTRAINT {VIEJA}")
        op.execute(f"ALTER TABLE modulo1.definicion_requisito ADD CONSTRAINT {NUEVA} UNIQUE NULLS NOT DISTINCT ({CLAVE})")

    _sin_force(_hacer)


def downgrade() -> None:
    def _hacer():
        op.execute(f"ALTER TABLE modulo1.definicion_requisito DROP CONSTRAINT IF EXISTS {NUEVA}")
        op.execute(f"ALTER TABLE modulo1.definicion_requisito ADD CONSTRAINT {VIEJA} UNIQUE ({CLAVE})")

    _sin_force(_hacer)
