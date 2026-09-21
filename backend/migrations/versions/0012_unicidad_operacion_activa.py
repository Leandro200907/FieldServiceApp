"""M-02: unicidad de excepciones y constancias ACTIVAS.

Claves de negocio (solo estados activos; las filas históricas —revocada, vencida,
regularizada, reemplazada— no participan y pueden ser muchas):
- excepción `otorgada`: una por (tenant, sujeto, requisito, commitment);
- constancia `vigente` GENERAL (commitment_id IS NULL): una por (tenant, sujeto, requisito, cliente);
- constancia `vigente` ESPECÍFICA: una por (tenant, sujeto, requisito, cliente, commitment).
Dos índices parciales para la constancia para que el NULL de commitment_id no haga
ambigua la clave. Los servicios cierran/reemplazan la fila anterior ANTES de insertar la
nueva y bloquean el legajo del sujeto como ancla para la primera creación; una colisión
residual llega como 23505 y se traduce a 409 de dominio.

Aborta con diagnóstico si ya existen duplicados activos (no elige ni borra ninguno).

Revision ID: 0012_unicidad_operacion_activa
Revises: 0011_tenant_fks
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_unicidad_operacion_activa"
down_revision = "0011_tenant_fks"
branch_labels = None
depends_on = None

DUPLICADOS = {
    "excepciones activas": (
        "SELECT tenant_id, sujeto_id, requisito_definicion_id, commitment_id, count(*) FROM modulo1.excepcion "
        "WHERE estado = 'otorgada' GROUP BY 1,2,3,4 HAVING count(*) > 1"
    ),
    "constancias generales activas": (
        "SELECT tenant_id, sujeto_id, requisito_definicion_id, cliente_id, count(*) FROM modulo1.constancia_cliente "
        "WHERE estado = 'vigente' AND commitment_id IS NULL GROUP BY 1,2,3,4 HAVING count(*) > 1"
    ),
    "constancias específicas activas": (
        "SELECT tenant_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id, count(*) FROM modulo1.constancia_cliente "
        "WHERE estado = 'vigente' AND commitment_id IS NOT NULL GROUP BY 1,2,3,4,5 HAVING count(*) > 1"
    ),
}


def _sin_force(tablas, fn):
    for t in tablas:
        op.execute(f"ALTER TABLE modulo1.{t} NO FORCE ROW LEVEL SECURITY")
    try:
        fn()
    finally:
        for t in tablas:
            op.execute(f"ALTER TABLE modulo1.{t} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    def _hacer():
        conn = op.get_bind()
        for nombre, sql in DUPLICADOS.items():
            filas = conn.execute(sa.text(sql)).all()
            if filas:
                raise RuntimeError(
                    f"0012 abortada: hay {len(filas)} grupos de {nombre} duplicadas; resolver a mano antes de migrar. "
                    f"Ejemplo: {tuple(filas[0])}"
                )
        op.execute(
            "CREATE UNIQUE INDEX uq_excepcion_activa ON modulo1.excepcion "
            "(tenant_id, sujeto_id, requisito_definicion_id, commitment_id) WHERE estado = 'otorgada'"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_constancia_general_activa ON modulo1.constancia_cliente "
            "(tenant_id, sujeto_id, requisito_definicion_id, cliente_id) WHERE estado = 'vigente' AND commitment_id IS NULL"
        )
        op.execute(
            "CREATE UNIQUE INDEX uq_constancia_especifica_activa ON modulo1.constancia_cliente "
            "(tenant_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id) WHERE estado = 'vigente' AND commitment_id IS NOT NULL"
        )

    _sin_force(("excepcion", "constancia_cliente"), _hacer)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.uq_constancia_especifica_activa")
    op.execute("DROP INDEX IF EXISTS modulo1.uq_constancia_general_activa")
    op.execute("DROP INDEX IF EXISTS modulo1.uq_excepcion_activa")
