"""H-02: Alerta de vencimiento como agregado persistente (especificacion 4.6, modelo 2.3/2.4).

- `configuracion_alertas` (una fila por tenant): plazo de aviso, N de escalamiento, rol de
  escalamiento configurable, días de silencio por reconocimiento. Sin fila → defaults.
- `definicion_requisito.plazo_aviso_dias`: override por tipo de requisito.
- `alerta_vencimiento`: única por (tenant, fuente_tipo, fuente_id); `etapa` (aviso ·
  recordatorio · vencido · escalado — función del tiempo) y `estado` (abierta ·
  pausada_por_accion · resuelta — función de la acción humana) como dimensiones
  independientes; `bajo_excepcion`; última acción registrada; destinatarios notificados
  en la etapa actual; reconocimiento con vencimiento.
- `alerta_notificacion`: mensajes pendientes por destinatario (rol / usuario) que el
  reloj agrupa (coalescing) en un solo job de `notificaciones` por destinatario y corrida.
- `aviso_oc_sin_matriz`: dedup del aviso "OC nueva sin matriz" (flujo 3.6 / 2.5).

Revision ID: 0017_alertas_vencimiento
Revises: 0016_plantillas_globales
"""
from alembic import op

revision = "0017_alertas_vencimiento"
down_revision = "0016_plantillas_globales"
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
    op.execute(
        """
        CREATE TABLE modulo1.configuracion_alertas (
            tenant_id UUID PRIMARY KEY REFERENCES modulo1.tenant(tenant_id),
            plazo_aviso_dias INTEGER NOT NULL DEFAULT 30 CHECK (plazo_aviso_dias BETWEEN 1 AND 365),
            escalamiento_dias INTEGER NOT NULL DEFAULT 7 CHECK (escalamiento_dias BETWEEN 0 AND 365),
            rol_escalamiento TEXT NOT NULL DEFAULT 'responsable_legajos'
                CHECK (rol_escalamiento IN ('configuracion', 'responsable_legajos', 'supervisor')),
            reconocimiento_dias INTEGER NOT NULL DEFAULT 3 CHECK (reconocimiento_dias BETWEEN 0 AND 30),
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_por TEXT
        )
        """
    )
    _rls("configuracion_alertas")
    op.execute("ALTER TABLE modulo1.definicion_requisito ADD COLUMN plazo_aviso_dias INTEGER CHECK (plazo_aviso_dias BETWEEN 1 AND 365)")

    op.execute(
        """
        CREATE TABLE modulo1.alerta_vencimiento (
            alerta_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            fuente_tipo TEXT NOT NULL CHECK (fuente_tipo IN ('documento', 'acreditacion_competencia', 'induccion', 'constancia_del_cliente')),
            fuente_id UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            tipo_sujeto TEXT NOT NULL CHECK (tipo_sujeto IN ('empresa', 'persona', 'vehiculo', 'equipo')),
            requisito_definicion_id UUID NOT NULL,
            vigente_hasta DATE NOT NULL,
            etapa TEXT NOT NULL CHECK (etapa IN ('aviso', 'recordatorio', 'vencido', 'escalado')),
            estado TEXT NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta', 'pausada_por_accion', 'resuelta')),
            bajo_excepcion BOOLEAN NOT NULL DEFAULT false,
            ultima_accion_tipo TEXT CHECK (ultima_accion_tipo IN ('carga_documento', 'excepcion', 'reconocimiento')),
            ultima_accion_en TIMESTAMPTZ,
            ultima_accion_ref TEXT,
            reconocida_hasta DATE,
            destinatarios_notificados_en_esta_etapa TEXT[] NOT NULL DEFAULT '{}',
            abierta_en DATE NOT NULL,
            etapa_desde DATE NOT NULL,
            escalada_en DATE,
            resuelta_en TIMESTAMPTZ,
            resuelta_motivo TEXT,
            resuelta_ref TEXT,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_alerta_fuente UNIQUE (tenant_id, fuente_tipo, fuente_id),
            CONSTRAINT uq_alerta_tenant_id UNIQUE (tenant_id, alerta_id),
            CONSTRAINT fk_alerta__sujeto_id FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo (tenant_id, sujeto_id),
            CONSTRAINT fk_alerta__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id)
                REFERENCES modulo1.definicion_requisito (tenant_id, requisito_definicion_id),
            CONSTRAINT ck_alerta_resuelta_coherente CHECK ((estado = 'resuelta') = (resuelta_en IS NOT NULL))
        )
        """
    )
    op.execute("CREATE INDEX ix_alerta_vencimiento_abiertas ON modulo1.alerta_vencimiento (tenant_id, etapa, sujeto_id) WHERE estado <> 'resuelta'")
    op.execute("CREATE INDEX ix_alerta_vencimiento_sujeto_req ON modulo1.alerta_vencimiento (tenant_id, sujeto_id, requisito_definicion_id)")
    _rls("alerta_vencimiento")

    op.execute(
        """
        CREATE TABLE modulo1.alerta_notificacion (
            notificacion_id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            alerta_id UUID NOT NULL,
            etapa TEXT NOT NULL,
            prioridad TEXT NOT NULL DEFAULT 'normal' CHECK (prioridad IN ('normal', 'alta')),
            destinatario_rol TEXT NOT NULL CHECK (destinatario_rol IN ('configuracion', 'responsable_legajos', 'supervisor', 'tecnico')),
            destinatario_usuario_id UUID,
            fecha DATE NOT NULL,
            creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            entregada_en TIMESTAMPTZ,
            job_id BIGINT,
            CONSTRAINT fk_alerta_notificacion__alerta_id FOREIGN KEY (tenant_id, alerta_id) REFERENCES modulo1.alerta_vencimiento (tenant_id, alerta_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_alerta_notificacion_pendientes ON modulo1.alerta_notificacion (tenant_id, destinatario_rol, destinatario_usuario_id) WHERE entregada_en IS NULL")
    _rls("alerta_notificacion")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE modulo1.alerta_notificacion_notificacion_id_seq TO modulo1_app")

    op.execute(
        """
        CREATE TABLE modulo1.aviso_oc_sin_matriz (
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            oc_id UUID NOT NULL,
            notificado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            evento_id UUID,
            PRIMARY KEY (tenant_id, oc_id)
        )
        """
    )
    _rls("aviso_oc_sin_matriz")


def downgrade() -> None:
    for tabla in ("aviso_oc_sin_matriz", "alerta_notificacion", "alerta_vencimiento", "configuracion_alertas"):
        op.execute(f"DROP TABLE IF EXISTS modulo1.{tabla}")
    op.execute("ALTER TABLE modulo1.definicion_requisito DROP COLUMN IF EXISTS plazo_aviso_dias")
