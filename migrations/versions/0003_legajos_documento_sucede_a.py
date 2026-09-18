"""documento.sucede_a — vínculo explícito con la versión que este documento sucedió.

Hace falta para RechazarPropuesta y RevertirLote: al anular una versión (propuesta
rechazada, lote revertido) hay que restaurar a `vigente` exactamente la versión que esa
anuló, no "la última sucedida" (que podría ser otra). Sin este puntero la restauración
sería una adivinanza sobre `version`/`creado_en`.

Revision ID: 0003_legajos_sucede_a
Revises: 0002_usuario_supervisor
"""
from alembic import op

revision = "0003_legajos_sucede_a"
down_revision = "0002_usuario_supervisor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Solo DDL: FORCE RLS impide a la migración tocar datos de tablas tenant-scoped.
    # La columna nace NULL para las filas existentes (no hay nada que backfillear:
    # antes de esta migración no se registraba el vínculo).
    op.execute(
        "ALTER TABLE modulo1.documento "
        "ADD COLUMN sucede_a UUID REFERENCES modulo1.documento(documento_id)"
    )
    op.execute("CREATE INDEX ix_documento_sucede_a ON modulo1.documento (tenant_id, sucede_a)")
    # documento ya tiene RLS ENABLE+FORCE+policy desde 0001; la columna nueva queda
    # cubierta por la misma policy. El GRANT sobre la tabla ya existe, se repite por
    # prolijidad (idempotente).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.documento TO modulo1_app")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.ix_documento_sucede_a")
    op.execute("ALTER TABLE modulo1.documento DROP COLUMN IF EXISTS sucede_a")
