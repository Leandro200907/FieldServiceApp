"""Espejo documental por operadora y alertas de sincronización.

Revision ID: 0022_espejo_operadoras
Revises: 0021_validacion_evidencia
"""
from alembic import op

revision = "0022_espejo_operadoras"
down_revision = "0021_validacion_evidencia"
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
    op.execute("""
        CREATE TABLE modulo1.operadora_documental (
            operadora_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            nombre TEXT NOT NULL,
            activa BOOLEAN NOT NULL DEFAULT true,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_operadora_documental_tenant_id UNIQUE (tenant_id, operadora_id)
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_operadora_documental_nombre ON modulo1.operadora_documental (tenant_id, lower(nombre))")

    op.execute("""
        CREATE TABLE modulo1.operadora_legajo (
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            operadora_id UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            fuente TEXT NOT NULL DEFAULT 'planilla',
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, operadora_id, sujeto_id),
            FOREIGN KEY (tenant_id, operadora_id) REFERENCES modulo1.operadora_documental(tenant_id, operadora_id),
            FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id)
        )
    """)

    op.execute("""
        CREATE TABLE modulo1.entrega_documento_operadora (
            entrega_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            operadora_id UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL,
            documento_id UUID NOT NULL,
            estado TEXT NOT NULL CHECK (estado IN ('exportado', 'enviado', 'aceptado', 'rechazado')),
            exportado_en TIMESTAMPTZ,
            enviado_en TIMESTAMPTZ,
            aceptado_en TIMESTAMPTZ,
            rechazado_en TIMESTAMPTZ,
            fuente_archivo TEXT,
            fuente_hoja TEXT,
            fuente_fila INTEGER CHECK (fuente_fila IS NULL OR fuente_fila > 0),
            observacion TEXT,
            actualizado_por TEXT NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_entrega_operadora_documento UNIQUE (tenant_id, operadora_id, documento_id),
            FOREIGN KEY (tenant_id, operadora_id, sujeto_id) REFERENCES modulo1.operadora_legajo(tenant_id, operadora_id, sujeto_id),
            FOREIGN KEY (tenant_id, documento_id) REFERENCES modulo1.documento(tenant_id, documento_id),
            FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id)
        )
    """)
    op.execute("CREATE INDEX ix_entrega_operadora_legajo ON modulo1.entrega_documento_operadora (tenant_id, sujeto_id, requisito_definicion_id, operadora_id)")

    op.execute("""
        CREATE TABLE modulo1.alerta_actualizacion_operadora (
            alerta_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            operadora_id UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL,
            documento_vigente_id UUID NOT NULL,
            ultimo_documento_operadora_id UUID,
            estado TEXT NOT NULL CHECK (estado IN ('pendiente_envio', 'pendiente_aceptacion', 'rechazado', 'resuelta')),
            motivo TEXT NOT NULL,
            abierta_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            resuelta_en TIMESTAMPTZ,
            CONSTRAINT uq_alerta_operadora_version UNIQUE (tenant_id, operadora_id, sujeto_id, requisito_definicion_id, documento_vigente_id),
            FOREIGN KEY (tenant_id, operadora_id) REFERENCES modulo1.operadora_documental(tenant_id, operadora_id),
            FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id),
            FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id),
            FOREIGN KEY (tenant_id, documento_vigente_id) REFERENCES modulo1.documento(tenant_id, documento_id),
            FOREIGN KEY (tenant_id, ultimo_documento_operadora_id) REFERENCES modulo1.documento(tenant_id, documento_id)
        )
    """)
    op.execute("CREATE INDEX ix_alerta_operadora_abierta ON modulo1.alerta_actualizacion_operadora (tenant_id, estado, sujeto_id) WHERE estado <> 'resuelta'")

    for tabla in ("operadora_documental", "operadora_legajo", "entrega_documento_operadora", "alerta_actualizacion_operadora"):
        _rls(tabla)


def downgrade() -> None:
    for tabla in ("alerta_actualizacion_operadora", "entrega_documento_operadora", "operadora_legajo", "operadora_documental"):
        op.execute(f"DROP TABLE IF EXISTS modulo1.{tabla} CASCADE")
