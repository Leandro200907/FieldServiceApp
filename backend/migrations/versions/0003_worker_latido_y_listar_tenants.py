"""Worker (8.6): latidos de procesos de reloj y función de sistema para iterar tenants.

- `modulo1.latido_proceso`: un registro por (proceso, tenant) con el último OK, el último
  error y un detalle. `tenant_id` NULL = latido global del worker. Todo proceso de reloj
  escribe acá; una alarma externa lee `ultimo_ok` y avisa si envejece.
- `modulo1.listar_tenants()`: el worker es un proceso de sistema y necesita iterar todos
  los tenants para drenar outbox y correr los procesos de reloj, pero el rol de app no
  ve `modulo1.tenant` sin contexto. Solución cerrada: función SECURITY DEFINER (owner)
  que devuelve solo los ids. Nunca BYPASSRLS.

Detalle no obvio: `tenant` tiene FORCE ROW LEVEL SECURITY, que aplica también al owner,
así que una función SECURITY DEFINER sola no alcanza — el owner tampoco ve filas sin
`app.current_tenant`. Se agrega una policy de SELECT restringida al rol owner
(`TO modulo1_owner`, USING (true)); el rol de app no la recibe y sigue viendo solo su
tenant. Esto también destraba `resolver_tenant_por_slug` (0002), que padecía lo mismo.

Revision ID: 0003_worker_latido
Revises: 0002_usuario_supervisor
"""
from alembic import op

revision = "0003_worker_latido"
down_revision = "0002_usuario_supervisor"
branch_labels = None
depends_on = None

UUID_NULO = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE modulo1.latido_proceso (
            latido_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nombre TEXT NOT NULL,
            tenant_id UUID REFERENCES modulo1.tenant(tenant_id) ON DELETE CASCADE,
            ultimo_ok TIMESTAMPTZ,
            ultimo_error TIMESTAMPTZ,
            detalle JSONB NOT NULL DEFAULT '{}'::jsonb,
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Unicidad por (proceso, tenant) tratando NULL como "global" — ON CONFLICT se apoya
    # en esta misma expresión.
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_latido_proceso ON modulo1.latido_proceso
        (nombre, (COALESCE(tenant_id, '{UUID_NULO}'::uuid)))
        """
    )
    # RLS igual que job_queue (tenant NULL visible desde cualquier contexto). Se usa la
    # variante `missing_ok` + NULLIF para que el latido global se pueda escribir desde
    # platform_session (sin tenant seteado, o con el placeholder vacío que queda tras
    # un SET LOCAL anterior en la misma conexión del pool).
    op.execute("ALTER TABLE modulo1.latido_proceso ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.latido_proceso FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY latido_proceso_aislamiento ON modulo1.latido_proceso
        USING (tenant_id IS NULL OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (tenant_id IS NULL OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.latido_proceso TO modulo1_app")

    # Policy de lectura solo para el owner (quien ejecuta las funciones SECURITY DEFINER).
    op.execute(
        """
        CREATE POLICY tenant_lectura_sistema ON modulo1.tenant
        FOR SELECT TO modulo1_owner USING (true)
        """
    )
    op.execute(
        """
        CREATE FUNCTION modulo1.listar_tenants() RETURNS SETOF UUID
        LANGUAGE sql SECURITY DEFINER STABLE AS $$
            SELECT tenant_id FROM modulo1.tenant ORDER BY creado_en, tenant_id
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION modulo1.listar_tenants() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION modulo1.listar_tenants() TO modulo1_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS modulo1.listar_tenants()")
    op.execute("DROP POLICY IF EXISTS tenant_lectura_sistema ON modulo1.tenant")
    op.execute("DROP TABLE IF EXISTS modulo1.latido_proceso")
