"""Catálogos con nombre para OC (operadora = cliente, locación, tipo de servicio).

Revision ID: 0028_catalogos_oc
Revises: 0026_lote_por_entidad
"""
from alembic import op

revision = "0028_catalogos_oc"
down_revision = "0026_lote_por_entidad"
branch_labels = None
depends_on = None

_POLICY = (
    "USING (tenant_id = current_setting('app.current_tenant')::uuid) "
    "WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)"
)


def _rls(tabla: str) -> None:
    op.execute(f"ALTER TABLE modulo1.{tabla} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE modulo1.{tabla} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {tabla}_aislamiento ON modulo1.{tabla} {_POLICY}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.{tabla} TO modulo1_app")


def upgrade() -> None:
    op.execute("ALTER TABLE modulo1.operadora_documental NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM modulo1.operadora_documental WHERE btrim(nombre) = ''")
    op.execute(
        "ALTER TABLE modulo1.operadora_documental "
        "ADD CONSTRAINT ck_operadora_documental_nombre CHECK (btrim(nombre) <> '')"
    )
    op.execute("ALTER TABLE modulo1.operadora_documental FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE TABLE modulo1.locacion_oc (
            locacion_id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            operadora_id UUID NOT NULL,
            nombre TEXT NOT NULL,
            activa BOOLEAN NOT NULL DEFAULT true,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_locacion_oc_tenant_id UNIQUE (tenant_id, locacion_id),
            FOREIGN KEY (tenant_id, operadora_id)
                REFERENCES modulo1.operadora_documental(tenant_id, operadora_id)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_locacion_oc_nombre "
        "ON modulo1.locacion_oc (tenant_id, operadora_id, lower(nombre))"
    )

    op.execute("""
        CREATE TABLE modulo1.tipo_servicio_oc (
            tipo_servicio_id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            nombre TEXT NOT NULL,
            activa BOOLEAN NOT NULL DEFAULT true,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_tipo_servicio_oc_tenant_id UNIQUE (tenant_id, tipo_servicio_id)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_tipo_servicio_oc_nombre "
        "ON modulo1.tipo_servicio_oc (tenant_id, lower(nombre))"
    )

    op.execute(
        "ALTER TABLE modulo1.oc ADD COLUMN IF NOT EXISTS origen_oc TEXT NOT NULL DEFAULT 'planilla'"
    )
    op.execute(
        "ALTER TABLE modulo1.oc ADD CONSTRAINT ck_oc_origen_oc "
        "CHECK (origen_oc IN ('planilla', 'manual', 'modulo2'))"
    )

    op.execute("""
        INSERT INTO modulo1.operadora_documental (operadora_id, tenant_id, nombre)
        SELECT DISTINCT cliente_id, tenant_id, 'Operadora ' || left(cliente_id::text, 8)
        FROM (
            SELECT cliente_id, tenant_id FROM modulo1.oc
            UNION
            SELECT cliente_id, tenant_id FROM modulo1.matriz_requisitos
        ) u
        ON CONFLICT (operadora_id) DO NOTHING
    """)

    op.execute("""
        INSERT INTO modulo1.locacion_oc (locacion_id, tenant_id, operadora_id, nombre)
        SELECT DISTINCT locacion_id, tenant_id, cliente_id,
               'Locación ' || left(locacion_id::text, 8)
        FROM (
            SELECT locacion_id, tenant_id, cliente_id FROM modulo1.oc
            UNION
            SELECT locacion_id, tenant_id, cliente_id FROM modulo1.matriz_requisitos
        ) u
        ON CONFLICT (locacion_id) DO NOTHING
    """)

    op.execute("""
        INSERT INTO modulo1.tipo_servicio_oc (tipo_servicio_id, tenant_id, nombre)
        SELECT DISTINCT tipo_servicio_id, tenant_id,
               'Servicio ' || left(tipo_servicio_id::text, 8)
        FROM (
            SELECT tipo_servicio_id, tenant_id FROM modulo1.oc
            UNION
            SELECT tipo_servicio_id, tenant_id FROM modulo1.matriz_requisitos
        ) u
        ON CONFLICT (tipo_servicio_id) DO NOTHING
    """)

    for tabla in ("locacion_oc", "tipo_servicio_oc"):
        _rls(tabla)


def downgrade() -> None:
    op.execute("ALTER TABLE modulo1.operadora_documental NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE modulo1.operadora_documental "
        "DROP CONSTRAINT IF EXISTS ck_operadora_documental_nombre"
    )
    op.execute("ALTER TABLE modulo1.operadora_documental FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.oc DROP CONSTRAINT IF EXISTS ck_oc_origen_oc")
    op.execute("ALTER TABLE modulo1.oc DROP COLUMN IF EXISTS origen_oc")
    for tabla in ("tipo_servicio_oc", "locacion_oc"):
        op.execute(f"DROP POLICY IF EXISTS {tabla}_aislamiento ON modulo1.{tabla}")
        op.execute(f"DROP TABLE IF EXISTS modulo1.{tabla}")
