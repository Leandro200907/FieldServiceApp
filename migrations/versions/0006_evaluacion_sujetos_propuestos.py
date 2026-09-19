"""A-04: la decisión de habilitación se toma sobre SUJETOS PROPUESTOS (modelo-dominio 2.1,
habilitante 1.5/1.5 bis) y esa relación es relacional, no un JSON.

- `evaluacion_habilitacion`: UNIQUE (tenant_id, referencia_evaluacion) para poder ser
  destino de una FK compuesta por tenant; columna `modo` fijada en 'decision' (el modo
  consulta NUNCA persiste — 2.1: "Consulta: no persiste, no crea tareas, no emite eventos").
- `legajo`: UNIQUE (tenant_id, sujeto_id) — un sujeto_id identifica un legajo dentro del
  tenant (la unicidad anterior incluía tipo_sujeto; el código ya usa sujeto_id solo).
- `evaluacion_sujeto_propuesto (tenant_id, evaluacion_id, sujeto_id, tipo_sujeto_al_proponer)`:
  `tipo_sujeto_al_proponer` es una FOTO del tipo del legajo al momento de decidir (parte
  del snapshot inmutable de 4.1), no un dato vivo: el tipo vivo se lee de `legajo`.
  PK compuesta (unicidad), FK compuesta a la evaluación y FK compuesta al legajo — ambas
  con tenant_id, así una fila jamás puede referenciar una evaluación o un legajo de otro
  tenant aunque RLS no estuviera. RLS + FORCE + policy como el resto.

`por_sujeto` (jsonb) y `snapshot` se conservan: son la foto histórica de la decisión y
no cambian retroactivamente; la tabla nueva es la verdad relacional de "quiénes fueron
propuestos" para autorización y consultas.

Revision ID: 0006_evaluacion_sujetos
Revises: 0005_storage_y_purga
"""
from alembic import op

revision = "0006_evaluacion_sujetos"
down_revision = "0005_storage_y_purga"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE modulo1.evaluacion_habilitacion "
        "ADD CONSTRAINT uq_evaluacion_tenant_ref UNIQUE (tenant_id, referencia_evaluacion)"
    )
    op.execute(
        "ALTER TABLE modulo1.evaluacion_habilitacion "
        "ADD COLUMN modo TEXT NOT NULL DEFAULT 'decision' CHECK (modo = 'decision')"
    )
    op.execute("ALTER TABLE modulo1.legajo ADD CONSTRAINT uq_legajo_tenant_sujeto UNIQUE (tenant_id, sujeto_id)")
    op.execute(
        """
        CREATE TABLE modulo1.evaluacion_sujeto_propuesto (
            tenant_id UUID NOT NULL,
            evaluacion_id UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            tipo_sujeto_al_proponer TEXT NOT NULL
                CONSTRAINT ck_esp_tipo_snapshot CHECK (tipo_sujeto_al_proponer IN ('persona', 'vehiculo', 'equipo')),
            PRIMARY KEY (tenant_id, evaluacion_id, sujeto_id),
            CONSTRAINT fk_esp_evaluacion FOREIGN KEY (tenant_id, evaluacion_id)
                REFERENCES modulo1.evaluacion_habilitacion (tenant_id, referencia_evaluacion) ON DELETE CASCADE,
            CONSTRAINT fk_esp_legajo FOREIGN KEY (tenant_id, sujeto_id)
                REFERENCES modulo1.legajo (tenant_id, sujeto_id)
        )
        """
    )
    op.execute(
        "COMMENT ON COLUMN modulo1.evaluacion_sujeto_propuesto.tipo_sujeto_al_proponer IS "
        "'Snapshot del tipo del legajo al momento de la decisión (4.1, inmutable). El tipo vivo está en legajo.tipo_sujeto.'"
    )
    op.execute("CREATE INDEX ix_esp_sujeto ON modulo1.evaluacion_sujeto_propuesto (tenant_id, sujeto_id)")
    op.execute("ALTER TABLE modulo1.evaluacion_sujeto_propuesto ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.evaluacion_sujeto_propuesto FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY evaluacion_sujeto_propuesto_aislamiento ON modulo1.evaluacion_sujeto_propuesto
        USING (tenant_id = current_setting('app.current_tenant')::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.evaluacion_sujeto_propuesto TO modulo1_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS modulo1.evaluacion_sujeto_propuesto")
    op.execute("ALTER TABLE modulo1.legajo DROP CONSTRAINT IF EXISTS uq_legajo_tenant_sujeto")
    op.execute("ALTER TABLE modulo1.evaluacion_habilitacion DROP COLUMN IF EXISTS modo")
    op.execute("ALTER TABLE modulo1.evaluacion_habilitacion DROP CONSTRAINT IF EXISTS uq_evaluacion_tenant_ref")
