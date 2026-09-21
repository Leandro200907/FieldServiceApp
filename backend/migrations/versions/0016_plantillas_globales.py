"""H-04: catálogo y matrices globales de industria con copia opt-in (no-funcionales 1.5.1–1.5.3).

plataforma (sin tenant_id, sin RLS; el rol app sólo lee):
- `definicion_requisito_global`: + `actualizado_en`, `descripcion`.
- `matriz_global` (una por operadora + tipo de servicio, versionada) y `linea_matriz_global`
  (referencia definiciones globales; clasificación y bloqueo en ejecución).

modulo1 (copias locales, autónomas):
- `definicion_requisito.copiada_de_version`: versión global con la que se copió.
- `matriz_requisitos.matriz_global_id` + `copiada_de_version`: origen de la versión local.
- `plantilla_aviso`: registro de `PlantillaGlobalActualizada` ya notificado por
  (tenant, tipo, plantilla, version_nueva) — el reloj notifica una sola vez por versión.

Precarga: `scripts/precargar_plantillas.py` (rol owner) desde `docs/plantillas/*.json`.

Revision ID: 0016_plantillas_globales
Revises: 0015_job_queue_dead_letter
"""
from alembic import op

revision = "0016_plantillas_globales"
down_revision = "0015_job_queue_dead_letter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE plataforma.definicion_requisito_global ADD COLUMN descripcion TEXT, ADD COLUMN actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()")
    op.execute(
        "ALTER TABLE plataforma.definicion_requisito_global "
        "ADD CONSTRAINT uq_definicion_global_clave UNIQUE (nombre, categoria, tipo_sujeto_aplicable)"
    )
    op.execute(
        """
        CREATE TABLE plataforma.matriz_global (
            matriz_global_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            operadora TEXT NOT NULL,
            tipo_servicio TEXT NOT NULL,
            descripcion TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            activa BOOLEAN NOT NULL DEFAULT true,
            fuente TEXT,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_matriz_global_clave UNIQUE (operadora, tipo_servicio)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE plataforma.linea_matriz_global (
            matriz_global_id UUID NOT NULL REFERENCES plataforma.matriz_global(matriz_global_id) ON DELETE CASCADE,
            definicion_global_id UUID NOT NULL REFERENCES plataforma.definicion_requisito_global(definicion_global_id),
            clasificacion TEXT NOT NULL CHECK (clasificacion IN ('bloqueante_duro', 'excepcionable')),
            bloqueante_durante_ejecucion BOOLEAN NOT NULL DEFAULT false,
            PRIMARY KEY (matriz_global_id, definicion_global_id)
        )
        """
    )
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA plataforma TO modulo1_app")

    op.execute("ALTER TABLE modulo1.definicion_requisito ADD COLUMN copiada_de_version INTEGER")
    # Copias locales previas a esta migración (alta manual con definicion_global_id) no
    # registraban la versión: se les asigna la versión global ACTUAL (a partir de acá el
    # reloj avisará cuando quede atrás). FORCE RLS se suspende sólo para este backfill.
    op.execute("ALTER TABLE modulo1.definicion_requisito NO FORCE ROW LEVEL SECURITY")
    try:
        op.execute(
            "UPDATE modulo1.definicion_requisito d SET copiada_de_version = g.version "
            "FROM plataforma.definicion_requisito_global g "
            "WHERE d.definicion_global_id = g.definicion_global_id AND d.copiada_de_version IS NULL"
        )
        op.execute(
            "ALTER TABLE modulo1.definicion_requisito ADD CONSTRAINT ck_definicion_copia_coherente CHECK "
            "((definicion_global_id IS NULL AND copiada_de_version IS NULL) OR (definicion_global_id IS NOT NULL AND copiada_de_version IS NOT NULL))"
        )
    finally:
        op.execute("ALTER TABLE modulo1.definicion_requisito FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE modulo1.matriz_requisitos "
        "ADD COLUMN matriz_global_id UUID REFERENCES plataforma.matriz_global(matriz_global_id), "
        "ADD COLUMN copiada_de_version INTEGER, "
        "ADD CONSTRAINT ck_matriz_copia_coherente CHECK "
        "((matriz_global_id IS NULL AND copiada_de_version IS NULL) OR (matriz_global_id IS NOT NULL AND copiada_de_version IS NOT NULL))"
    )
    op.execute(
        """
        CREATE TABLE modulo1.plantilla_aviso (
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            plantilla_tipo TEXT NOT NULL CHECK (plantilla_tipo IN ('matriz', 'definicion_requisito')),
            plantilla_global_id UUID NOT NULL,
            version_nueva INTEGER NOT NULL,
            notificado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            evento_id UUID,
            PRIMARY KEY (tenant_id, plantilla_tipo, plantilla_global_id, version_nueva)
        )
        """
    )
    op.execute("ALTER TABLE modulo1.plantilla_aviso ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.plantilla_aviso FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY plantilla_aviso_aislamiento ON modulo1.plantilla_aviso "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.plantilla_aviso TO modulo1_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS modulo1.plantilla_aviso")
    op.execute("ALTER TABLE modulo1.matriz_requisitos DROP CONSTRAINT IF EXISTS ck_matriz_copia_coherente, DROP COLUMN IF EXISTS copiada_de_version, DROP COLUMN IF EXISTS matriz_global_id")
    op.execute("ALTER TABLE modulo1.definicion_requisito DROP CONSTRAINT IF EXISTS ck_definicion_copia_coherente, DROP COLUMN IF EXISTS copiada_de_version")
    op.execute("DROP TABLE IF EXISTS plataforma.linea_matriz_global")
    op.execute("DROP TABLE IF EXISTS plataforma.matriz_global")
    op.execute("ALTER TABLE plataforma.definicion_requisito_global DROP CONSTRAINT IF EXISTS uq_definicion_global_clave, DROP COLUMN IF EXISTS actualizado_en, DROP COLUMN IF EXISTS descripcion")
