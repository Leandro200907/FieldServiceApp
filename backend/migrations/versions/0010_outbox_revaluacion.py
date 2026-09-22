"""A-07: política de revaluación (tabla 7.2) con avisos normalizados, dedup por evento
causal y outbox con clave de deduplicación.

- `event_log`: UNIQUE (tenant_id, evento_id) — el evento_id es la identidad inmutable del
  evento causal y destino de FKs compuestas.
- `politica_evento_procesado`: cada (tenant_id, evento_id) pasa por la política UNA vez.
  Reprocesar un evento antiguo (p. ej. después de que una decisión nueva cerró el aviso)
  no vuelve a abrir nada.
- `evaluacion_habilitacion`: `secuencia BIGSERIAL` (desempate determinista e inmutable de
  "última decisión": ORDER BY creado_en DESC, secuencia DESC; creado_en lo genera la base)
  y `origen_sujetos` (explicito | custodia_por_defecto), que solo fija el servidor.
- `aviso_revaluacion` (+ `_causa`): un aviso abierto por evaluación (único parcial),
  causas normalizadas únicas por (aviso, evento_id).
- `aviso_incumplimiento_empresa` (+ `_causa`): un aviso abierto por tenant (único
  parcial), una causa ACTIVA por (aviso, requisito) (único parcial); las regularizadas
  quedan como auditoría.
- `outbox_events`: `clave_dedup` UNIQUE por tenant + `version_contrato`.
- Índices para los selectores: decisiones por commitment/orden, por versión de matriz,
  OC por clave de matriz.

Revision ID: 0010_outbox_revaluacion
Revises: 0009_idempotencia_actor
"""
from alembic import op

revision = "0010_outbox_revaluacion"
down_revision = "0009_idempotencia_actor"
branch_labels = None
depends_on = None

TABLAS_RLS = (
    "politica_evento_procesado",
    "aviso_revaluacion",
    "aviso_revaluacion_causa",
    "aviso_incumplimiento_empresa",
    "aviso_incumplimiento_empresa_causa",
)


def upgrade() -> None:
    # --- identidad de eventos y outbox
    op.execute("ALTER TABLE modulo1.event_log ADD CONSTRAINT uq_event_log_tenant_evento UNIQUE (tenant_id, evento_id)")
    op.execute(
        """
        ALTER TABLE modulo1.outbox_events
            ADD COLUMN clave_dedup TEXT,
            ADD COLUMN version_contrato TEXT NOT NULL DEFAULT '1.0',
            ADD CONSTRAINT uq_outbox_dedup UNIQUE (tenant_id, clave_dedup)
        """
    )
    op.execute(
        """
        CREATE TABLE modulo1.politica_evento_procesado (
            tenant_id UUID NOT NULL,
            evento_id UUID NOT NULL,
            tipo TEXT NOT NULL,
            procesado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, evento_id),
            CONSTRAINT fk_pep_evento FOREIGN KEY (tenant_id, evento_id)
                REFERENCES modulo1.event_log (tenant_id, evento_id) ON DELETE CASCADE
        )
        """
    )

    # --- decisiones: orden determinista y origen de sujetos
    op.execute(
        """
        ALTER TABLE modulo1.evaluacion_habilitacion
            ADD COLUMN secuencia BIGSERIAL,
            ADD COLUMN origen_sujetos TEXT NOT NULL DEFAULT 'explicito'
                CONSTRAINT ck_eval_origen_sujetos CHECK (origen_sujetos IN ('explicito', 'custodia_por_defecto'))
        """
    )
    op.execute(
        "CREATE INDEX ix_eval_commitment_orden ON modulo1.evaluacion_habilitacion "
        "(tenant_id, commitment_id, creado_en DESC, secuencia DESC)"
    )
    op.execute(
        "CREATE INDEX ix_eval_version_matriz ON modulo1.evaluacion_habilitacion "
        "(tenant_id, (version_matriz->>'matriz_version_id'))"
    )
    op.execute("CREATE INDEX ix_oc_clave_matriz ON modulo1.oc (tenant_id, cliente_id, locacion_id, tipo_servicio_id)")
    op.execute(
        "ALTER TABLE modulo1.definicion_requisito ADD CONSTRAINT uq_definicion_tenant_id UNIQUE (tenant_id, requisito_definicion_id)"
    )

    # --- aviso de revaluación (2.2 de modelo-dominio)
    op.execute(
        """
        CREATE TABLE modulo1.aviso_revaluacion (
            aviso_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            referencia_evaluacion UUID NOT NULL,
            commitment_id TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'cerrado')),
            abierto_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            cerrado_en TIMESTAMPTZ,
            cerrado_por_referencia UUID,
            CONSTRAINT uq_aviso_tenant_id UNIQUE (tenant_id, aviso_id),
            CONSTRAINT fk_aviso_evaluacion FOREIGN KEY (tenant_id, referencia_evaluacion)
                REFERENCES modulo1.evaluacion_habilitacion (tenant_id, referencia_evaluacion) ON DELETE CASCADE,
            CONSTRAINT ck_aviso_cierre CHECK ((estado = 'abierto' AND cerrado_en IS NULL) OR (estado = 'cerrado' AND cerrado_en IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_aviso_revaluacion_abierto ON modulo1.aviso_revaluacion (tenant_id, referencia_evaluacion) "
        "WHERE estado = 'abierto'"
    )
    op.execute("CREATE INDEX ix_aviso_revaluacion_commitment ON modulo1.aviso_revaluacion (tenant_id, commitment_id, estado)")
    op.execute(
        """
        CREATE TABLE modulo1.aviso_revaluacion_causa (
            tenant_id UUID NOT NULL,
            aviso_id UUID NOT NULL,
            evento_id UUID NOT NULL,
            tipo_evento TEXT NOT NULL,
            entidad_tipo TEXT NOT NULL,
            entidad_id TEXT NOT NULL,
            registrada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, aviso_id, evento_id),
            CONSTRAINT fk_arc_aviso FOREIGN KEY (tenant_id, aviso_id)
                REFERENCES modulo1.aviso_revaluacion (tenant_id, aviso_id) ON DELETE CASCADE,
            CONSTRAINT fk_arc_evento FOREIGN KEY (tenant_id, evento_id)
                REFERENCES modulo1.event_log (tenant_id, evento_id) ON DELETE CASCADE
        )
        """
    )

    # --- aviso de incumplimiento de empresa (2.9 de modelo-dominio)
    op.execute(
        """
        CREATE TABLE modulo1.aviso_incumplimiento_empresa (
            aviso_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            estado TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'regularizado')),
            desde DATE NOT NULL,
            abierto_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            regularizado_en TIMESTAMPTZ,
            CONSTRAINT uq_aie_tenant_id UNIQUE (tenant_id, aviso_id),
            CONSTRAINT ck_aie_cierre CHECK ((estado = 'abierto' AND regularizado_en IS NULL) OR (estado = 'regularizado' AND regularizado_en IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_aie_abierto_por_tenant ON modulo1.aviso_incumplimiento_empresa (tenant_id) WHERE estado = 'abierto'"
    )
    op.execute(
        """
        CREATE TABLE modulo1.aviso_incumplimiento_empresa_causa (
            causa_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            aviso_id UUID NOT NULL,
            requisito_definicion_id UUID NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'regularizada')),
            desde DATE NOT NULL,
            registrada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            regularizada_en TIMESTAMPTZ,
            CONSTRAINT fk_aiec_aviso FOREIGN KEY (tenant_id, aviso_id)
                REFERENCES modulo1.aviso_incumplimiento_empresa (tenant_id, aviso_id) ON DELETE CASCADE,
            CONSTRAINT fk_aiec_requisito FOREIGN KEY (tenant_id, requisito_definicion_id)
                REFERENCES modulo1.definicion_requisito (tenant_id, requisito_definicion_id),
            CONSTRAINT ck_aiec_cierre CHECK ((estado = 'activa' AND regularizada_en IS NULL) OR (estado = 'regularizada' AND regularizada_en IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_aiec_activa ON modulo1.aviso_incumplimiento_empresa_causa (tenant_id, aviso_id, requisito_definicion_id) "
        "WHERE estado = 'activa'"
    )

    for tabla in TABLAS_RLS:
        op.execute(f"ALTER TABLE modulo1.{tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE modulo1.{tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tabla}_aislamiento ON modulo1.{tabla}
            USING (tenant_id = current_setting('app.current_tenant')::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON modulo1.{tabla} TO modulo1_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA modulo1 TO modulo1_app")


def downgrade() -> None:
    for tabla in reversed(TABLAS_RLS):
        op.execute(f"DROP TABLE IF EXISTS modulo1.{tabla}")
    op.execute("ALTER TABLE modulo1.definicion_requisito DROP CONSTRAINT IF EXISTS uq_definicion_tenant_id")
    op.execute("DROP INDEX IF EXISTS modulo1.ix_oc_clave_matriz")
    op.execute("DROP INDEX IF EXISTS modulo1.ix_eval_version_matriz")
    op.execute("DROP INDEX IF EXISTS modulo1.ix_eval_commitment_orden")
    op.execute(
        "ALTER TABLE modulo1.evaluacion_habilitacion DROP COLUMN IF EXISTS origen_sujetos, DROP COLUMN IF EXISTS secuencia"
    )
    op.execute(
        "ALTER TABLE modulo1.outbox_events DROP CONSTRAINT IF EXISTS uq_outbox_dedup, "
        "DROP COLUMN IF EXISTS version_contrato, DROP COLUMN IF EXISTS clave_dedup"
    )
    op.execute("ALTER TABLE modulo1.event_log DROP CONSTRAINT IF EXISTS uq_event_log_tenant_evento")
