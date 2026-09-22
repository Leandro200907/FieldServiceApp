"""usuario (identidad para JWT propio, 9.2) y asignacion_supervisor (pieza del modelo de dominio
"Asignación de supervisor" que 0001 no incluyó).

Revision ID: 0002_usuario_supervisor
Revises: 0001_initial_schema
"""
from alembic import op

revision = "0002_usuario_supervisor"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

ROLES = ("configuracion", "responsable_legajos", "supervisor", "tecnico")


def upgrade() -> None:
    # Usuario del sistema ≠ Legajo (2.1 de no-funcionales). Roles múltiples por usuario.
    # sujeto_id vinculado: obligatorio para técnico (1:1 con su propio Legajo), opcional
    # para supervisor.
    op.execute(
        f"""
        CREATE TABLE modulo1.usuario (
            usuario_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            email TEXT NOT NULL,
            nombre TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            roles TEXT[] NOT NULL,
            sujeto_id TEXT,
            activo BOOLEAN NOT NULL DEFAULT true,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_usuario_tenant_email UNIQUE (tenant_id, email),
            CONSTRAINT ck_usuario_roles_no_vacio CHECK (array_length(roles, 1) > 0),
            CONSTRAINT ck_usuario_roles_validos CHECK (roles <@ ARRAY{list(ROLES)}::text[])
        )
        """
    )
    # Refresh tokens revocables (9.2): se guarda solo el hash del token.
    op.execute(
        """
        CREATE TABLE modulo1.refresh_token (
            token_hash TEXT PRIMARY KEY,
            tenant_id UUID NOT NULL,
            usuario_id UUID NOT NULL REFERENCES modulo1.usuario(usuario_id),
            expira_en TIMESTAMPTZ NOT NULL,
            revocado_en TIMESTAMPTZ,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_refresh_token_usuario ON modulo1.refresh_token (tenant_id, usuario_id)")

    # Asignación de supervisor (dominio Evidencia): historial, una vigente por sujeto.
    op.execute(
        """
        CREATE TABLE modulo1.asignacion_supervisor (
            asignacion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            supervisor_usuario_id UUID NOT NULL,
            desde DATE NOT NULL,
            hasta DATE,
            estado TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'cerrada')),
            asignada_por TEXT NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_asignacion_hasta CHECK ((estado = 'vigente' AND hasta IS NULL) OR estado <> 'vigente')
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_asignacion_supervisor_vigente ON modulo1.asignacion_supervisor (tenant_id, sujeto_id) WHERE estado = 'vigente'"
    )
    op.execute("CREATE INDEX ix_asignacion_supervisor_sup ON modulo1.asignacion_supervisor (tenant_id, supervisor_usuario_id)")

    for tabla in ("usuario", "refresh_token", "asignacion_supervisor"):
        op.execute(f"ALTER TABLE modulo1.{tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE modulo1.{tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tabla}_aislamiento ON modulo1.{tabla}
            USING (tenant_id = current_setting('app.current_tenant')::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)
            """
        )
    # Login: todavía no hay tenant en sesión. Se resuelve por email+tenant_slug ANTES de
    # abrir tenant_session — ver app/auth. Para eso el tenant necesita un slug público.
    # (FORCE RLS aplica también al owner, así que no se puede hacer UPDATE de backfill
    # desde la migración: el DEFAULT rellena las filas existentes en el mismo DDL.)
    op.execute("ALTER TABLE modulo1.tenant ADD COLUMN slug TEXT NOT NULL DEFAULT gen_random_uuid()::text")
    op.execute("ALTER TABLE modulo1.tenant ALTER COLUMN slug DROP DEFAULT")
    op.execute("CREATE UNIQUE INDEX uq_tenant_slug ON modulo1.tenant (slug)")
    # Función SECURITY DEFINER (owner) para resolver tenant por slug sin abrir el RLS de
    # tenant al rol de app: devuelve solo el tenant_id, nada más.
    op.execute(
        """
        CREATE FUNCTION modulo1.resolver_tenant_por_slug(p_slug TEXT) RETURNS UUID
        LANGUAGE sql SECURITY DEFINER STABLE AS $$
            SELECT tenant_id FROM modulo1.tenant WHERE slug = p_slug
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION modulo1.resolver_tenant_por_slug(TEXT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION modulo1.resolver_tenant_por_slug(TEXT) TO modulo1_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA modulo1 TO modulo1_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS modulo1.resolver_tenant_por_slug(TEXT)")
    op.execute("DROP INDEX IF EXISTS modulo1.uq_tenant_slug")
    op.execute("ALTER TABLE modulo1.tenant DROP COLUMN IF EXISTS slug")
    op.execute("DROP TABLE IF EXISTS modulo1.asignacion_supervisor")
    op.execute("DROP TABLE IF EXISTS modulo1.refresh_token")
    op.execute("DROP TABLE IF EXISTS modulo1.usuario")
