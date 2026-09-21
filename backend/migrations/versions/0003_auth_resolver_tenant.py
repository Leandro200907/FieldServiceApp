"""Login sin tenant en sesión: `resolver_tenant_por_slug` no podía leer `modulo1.tenant`.

0002 creó la función como SECURITY DEFINER (corre como owner) esperando saltear el RLS de
`tenant`, pero `tenant` tiene FORCE ROW LEVEL SECURITY (0001), que aplica también al
owner, y la policy evalúa `current_setting('app.current_tenant')` — que en login todavía
no está fijado → error "parámetro de configuración no reconocido". No hay forma de
saltear una policy FORCE sin BYPASSRLS (que el owner no tiene, a propósito).

Solución mínima y sin tocar la policy de `tenant`: una tabla espejo `tenant_slug`
(slug → tenant_id, nada más) SIN RLS, mantenida por trigger sobre `tenant`, que es lo
único que la función lee. El rol de aplicación no tiene GRANT sobre `tenant_slug`: solo
la ve a través de la función, que sigue devolviendo únicamente el tenant_id.

Revision ID: 0003_auth_resolver_tenant
Revises: 0002_usuario_supervisor
"""
from alembic import op

revision = "0003_auth_resolver_tenant"
down_revision = "0002_usuario_supervisor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE modulo1.tenant_slug (
            slug TEXT PRIMARY KEY,
            tenant_id UUID NOT NULL UNIQUE
        )
        """
    )
    # Trigger SECURITY DEFINER: la fila la escribe el owner aunque el INSERT en `tenant`
    # lo haga el rol de aplicación (que no tiene permisos sobre `tenant_slug`).
    op.execute(
        """
        CREATE FUNCTION modulo1.sincronizar_tenant_slug() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER AS $$
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                DELETE FROM modulo1.tenant_slug WHERE tenant_id = OLD.tenant_id;
            END IF;
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                INSERT INTO modulo1.tenant_slug (slug, tenant_id) VALUES (NEW.slug, NEW.tenant_id);
                RETURN NEW;
            END IF;
            RETURN OLD;
        END
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION modulo1.sincronizar_tenant_slug() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_tenant_slug
        AFTER INSERT OR UPDATE OF slug, tenant_id OR DELETE ON modulo1.tenant
        FOR EACH ROW EXECUTE FUNCTION modulo1.sincronizar_tenant_slug()
        """
    )
    # Backfill de tenants existentes. Único lugar donde una migración lee una tabla
    # tenant-scoped: se suspende FORCE solo durante esta transacción (el owner sin FORCE
    # no está sujeto a la policy) y se restablece antes de terminar.
    op.execute("ALTER TABLE modulo1.tenant NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO modulo1.tenant_slug (slug, tenant_id) SELECT slug, tenant_id FROM modulo1.tenant "
        "ON CONFLICT DO NOTHING"
    )
    op.execute("ALTER TABLE modulo1.tenant FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION modulo1.resolver_tenant_por_slug(p_slug TEXT) RETURNS UUID
        LANGUAGE sql SECURITY DEFINER STABLE AS $$
            SELECT tenant_id FROM modulo1.tenant_slug WHERE slug = p_slug
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION modulo1.resolver_tenant_por_slug(p_slug TEXT) RETURNS UUID
        LANGUAGE sql SECURITY DEFINER STABLE AS $$
            SELECT tenant_id FROM modulo1.tenant WHERE slug = p_slug
        $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_tenant_slug ON modulo1.tenant")
    op.execute("DROP FUNCTION IF EXISTS modulo1.sincronizar_tenant_slug()")
    op.execute("DROP TABLE IF EXISTS modulo1.tenant_slug")
