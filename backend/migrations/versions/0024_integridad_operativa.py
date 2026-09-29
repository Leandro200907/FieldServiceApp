"""Endurece retención documental y unicidad de legajos activos.

Revision ID: 0024_integridad_operativa
Revises: 0023_documento_unificado
"""
from alembic import op


revision = "0024_integridad_operativa"
down_revision = "0023_documento_unificado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Toda función SECURITY DEFINER debe resolver nombres sobre esquemas cerrados;
    # nunca heredar el search_path manipulable de quien la invoca.
    op.execute(
        "ALTER FUNCTION modulo1.sincronizar_tenant_slug() "
        "SET search_path = pg_catalog, modulo1"
    )
    op.execute(
        "ALTER FUNCTION modulo1.resolver_tenant_por_slug(TEXT) "
        "SET search_path = pg_catalog, modulo1"
    )
    op.execute(
        "ALTER FUNCTION modulo1.listar_tenants() "
        "SET search_path = pg_catalog, modulo1"
    )

    # La retención empieza cuando una versión deja de ser vigente, no cuando fue creada.
    # Para históricos previos no conocemos el instante real: `now()` evita una purga
    # inmediata al desplegar y abre un período de retención completo desde la migración.
    op.execute("ALTER TABLE modulo1.documento ADD COLUMN dejo_de_ser_vigente_en TIMESTAMPTZ")
    op.execute(
        "UPDATE modulo1.documento SET dejo_de_ser_vigente_en = now() "
        "WHERE estado_version <> 'vigente'"
    )
    op.execute(
        "UPDATE modulo1.documento SET archivo_estado = 'confirmado' "
        "WHERE estado_version = 'sucedida' AND archivo_estado = 'purga_pendiente'"
    )
    op.execute("""
        CREATE FUNCTION modulo1.marcar_cambio_vigencia_documento() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, modulo1 AS $$
        BEGIN
            IF NEW.estado_version = 'vigente' THEN
                NEW.dejo_de_ser_vigente_en := NULL;
            ELSIF OLD.estado_version IS DISTINCT FROM NEW.estado_version THEN
                NEW.dejo_de_ser_vigente_en := now();
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_documento_cambio_vigencia
        BEFORE UPDATE OF estado_version ON modulo1.documento
        FOR EACH ROW EXECUTE FUNCTION modulo1.marcar_cambio_vigencia_documento()
    """)

    # La aplicación y los importadores comparan identificadores sin distinguir
    # mayúsculas ni espacios exteriores. La base debe imponer la misma identidad.
    op.execute("""
        CREATE UNIQUE INDEX uq_legajo_identificador_activo
        ON modulo1.legajo (tenant_id, tipo_sujeto, lower(btrim(identificador_natural)))
        WHERE dado_de_baja_en IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS modulo1.uq_legajo_identificador_activo")
    op.execute("DROP TRIGGER IF EXISTS trg_documento_cambio_vigencia ON modulo1.documento")
    op.execute("DROP FUNCTION IF EXISTS modulo1.marcar_cambio_vigencia_documento()")
    op.execute("ALTER TABLE modulo1.documento DROP COLUMN IF EXISTS dejo_de_ser_vigente_en")
    op.execute("ALTER FUNCTION modulo1.sincronizar_tenant_slug() RESET search_path")
    op.execute("ALTER FUNCTION modulo1.resolver_tenant_por_slug(TEXT) RESET search_path")
    op.execute("ALTER FUNCTION modulo1.listar_tenants() RESET search_path")
