"""Movimientos append-only del espejo documental por operadora.

Revision ID: 0029_mov_operadora
Revises: 0028_catalogos_oc
"""
from alembic import op

revision = "0029_mov_operadora"
down_revision = "0028_catalogos_oc"
branch_labels = None
depends_on = None

_POLICY = (
    "USING (tenant_id = current_setting('app.current_tenant')::uuid) "
    "WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)"
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE modulo1.movimiento_entrega_operadora (
            movimiento_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            operadora_id UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL,
            documento_id UUID NOT NULL,
            estado TEXT NOT NULL CHECK (estado IN ('exportado', 'enviado', 'aceptado', 'rechazado')),
            paso_en TIMESTAMPTZ NOT NULL,
            observacion TEXT,
            registrado_por TEXT NOT NULL,
            origen TEXT NOT NULL CHECK (origen IN ('planilla', 'manual')),
            fuente_archivo TEXT,
            fuente_hoja TEXT,
            fuente_fila INTEGER CHECK (fuente_fila IS NULL OR fuente_fila > 0),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            FOREIGN KEY (tenant_id, operadora_id) REFERENCES modulo1.operadora_documental(tenant_id, operadora_id),
            FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id),
            FOREIGN KEY (tenant_id, documento_id) REFERENCES modulo1.documento(tenant_id, documento_id),
            FOREIGN KEY (tenant_id, requisito_definicion_id)
                REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id)
        )
    """)
    op.execute(
        "CREATE INDEX ix_mov_operadora_legajo ON modulo1.movimiento_entrega_operadora "
        "(tenant_id, operadora_id, sujeto_id, requisito_definicion_id, paso_en DESC)"
    )
    op.execute(
        "CREATE INDEX ix_mov_operadora_documento ON modulo1.movimiento_entrega_operadora "
        "(tenant_id, documento_id, paso_en DESC)"
    )

    op.execute("ALTER TABLE modulo1.movimiento_entrega_operadora NO FORCE ROW LEVEL SECURITY")

    op.execute("""
        INSERT INTO modulo1.movimiento_entrega_operadora (
            tenant_id, operadora_id, sujeto_id, requisito_definicion_id, documento_id,
            estado, paso_en, observacion, registrado_por, origen,
            fuente_archivo, fuente_hoja, fuente_fila, creado_en
        )
        SELECT
            e.tenant_id,
            (e.payload->>'operadora_id')::uuid,
            e.payload->>'sujeto_id',
            d.requisito_definicion_id,
            (e.payload->>'documento_id')::uuid,
            e.payload->>'estado',
            e.ocurrido_en,
            NULL,
            COALESCE(e.payload->>'usuario_id', 'sistema'),
            CASE
                WHEN COALESCE(e.payload->>'fuente_archivo', '') <> '' THEN 'planilla'
                ELSE 'manual'
            END,
            NULLIF(e.payload->>'fuente_archivo', ''),
            NULLIF(e.payload->>'fuente_hoja', ''),
            NULLIF(e.payload->>'fuente_fila', '')::integer,
            e.ocurrido_en
        FROM modulo1.event_log e
        JOIN modulo1.documento d
          ON d.tenant_id = e.tenant_id
         AND d.documento_id = (e.payload->>'documento_id')::uuid
        WHERE e.tipo = 'EstadoDocumentoOperadoraRegistrado'
        ORDER BY e.ocurrido_en
    """)

    op.execute("""
        INSERT INTO modulo1.movimiento_entrega_operadora (
            tenant_id, operadora_id, sujeto_id, requisito_definicion_id, documento_id,
            estado, paso_en, observacion, registrado_por, origen,
            fuente_archivo, fuente_hoja, fuente_fila, creado_en
        )
        SELECT
            ent.tenant_id, ent.operadora_id, ent.sujeto_id, ent.requisito_definicion_id, ent.documento_id,
            ent.estado,
            COALESCE(ent.rechazado_en, ent.aceptado_en, ent.enviado_en, ent.exportado_en, ent.actualizado_en),
            ent.observacion,
            ent.actualizado_por,
            CASE WHEN ent.fuente_archivo IS NOT NULL THEN 'planilla' ELSE 'manual' END,
            ent.fuente_archivo, ent.fuente_hoja, ent.fuente_fila,
            ent.creado_en
        FROM modulo1.entrega_documento_operadora ent
        WHERE NOT EXISTS (
            SELECT 1 FROM modulo1.movimiento_entrega_operadora m
            WHERE m.tenant_id = ent.tenant_id AND m.documento_id = ent.documento_id
              AND m.operadora_id = ent.operadora_id
        )
    """)

    op.execute("ALTER TABLE modulo1.movimiento_entrega_operadora ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.movimiento_entrega_operadora FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY movimiento_entrega_operadora_aislamiento "
        f"ON modulo1.movimiento_entrega_operadora {_POLICY}"
    )
    op.execute("GRANT SELECT, INSERT ON modulo1.movimiento_entrega_operadora TO modulo1_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS modulo1.movimiento_entrega_operadora CASCADE")
