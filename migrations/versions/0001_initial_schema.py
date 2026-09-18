"""Schema inicial — 8.1 de modulo1-arquitectura-tecnica.md al pie de la letra.

Implementa:
- Dos schemas: `modulo1` (tenant-scoped, con RLS) y `plataforma` (catálogo global de
  industria, sin tenant_id, sin RLS — decisión 4 de 8.1).
- `tenant_id` primero en todo índice compuesto (decisión 6).
- FORCE ROW LEVEL SECURITY en toda tabla de `modulo1` (decisión 2) — el rol de
  aplicación (`modulo1_app`) no es owner y no tiene BYPASSRLS, así que ni siquiera
  puede saltarse la política aunque quisiera.
- Entidades de modulo1-especificacion.md, secciones 2-4, con los nombres de campo
  exactos que ahí se cerraron. Alcance de esta primera migración: las piezas
  necesarias para el motor de evaluación + el backlog de OC standalone (1.12 de
  documentacion-habilitante.md) + la infraestructura de 8.2-8.4 (idempotencia,
  outbox, cola). Quedan para una migración siguiente: Aviso de revaluación, Aviso de
  incumplimiento de empresa, Alerta de vencimiento — no bloquean el motor ni el API
  mínimo, y así se evita entregar una migración gigante sin poder probarla.
"""
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid()

    op.execute("CREATE SCHEMA IF NOT EXISTS modulo1")
    op.execute("CREATE SCHEMA IF NOT EXISTS plataforma")

    # ------------------------------------------------------------------
    # plataforma — catálogo global de industria. Sin tenant_id, sin RLS.
    # El rol de aplicación solo tiene SELECT (grant al final del archivo).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE plataforma.definicion_requisito_global (
            definicion_global_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL CHECK (categoria IN ('documento', 'competencia', 'induccion')),
            tipo_sujeto_aplicable TEXT NOT NULL CHECK (tipo_sujeto_aplicable IN ('empresa', 'persona', 'vehiculo', 'equipo')),
            version INTEGER NOT NULL DEFAULT 1,
            activa BOOLEAN NOT NULL DEFAULT true,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ------------------------------------------------------------------
    # modulo1 — tablas tenant-scoped. Todas con tenant_id + RLS.
    # ------------------------------------------------------------------

    op.execute(
        """
        CREATE TABLE modulo1.tenant (
            tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            nombre TEXT NOT NULL,
            zona_horaria TEXT NOT NULL DEFAULT 'America/Argentina/Buenos_Aires',
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # tenant no lleva RLS propia (nadie consulta "todos los tenants" desde el rol de
    # aplicación en operación normal) pero sí FORCE RLS con una política que solo deja
    # ver la fila del propio tenant — evita que un bug filtre nombres de otros tenants.
    op.execute("ALTER TABLE modulo1.tenant ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE modulo1.tenant FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_aislamiento ON modulo1.tenant
        USING (tenant_id = current_setting('app.current_tenant')::uuid)
        """
    )

    op.execute(
        """
        CREATE TABLE modulo1.definicion_requisito (
            requisito_definicion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL CHECK (categoria IN ('documento', 'competencia', 'induccion')),
            tipo_sujeto_aplicable TEXT NOT NULL CHECK (tipo_sujeto_aplicable IN ('empresa', 'persona', 'vehiculo', 'equipo')),
            locacion_id UUID,
            activa BOOLEAN NOT NULL DEFAULT true,
            definicion_global_id UUID REFERENCES plataforma.definicion_requisito_global(definicion_global_id),
            plazo_retencion_archivo INTERVAL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT induccion_requiere_locacion CHECK (
                (categoria = 'induccion' AND locacion_id IS NOT NULL) OR
                (categoria != 'induccion' AND locacion_id IS NULL)
            ),
            CONSTRAINT uq_definicion_requisito UNIQUE (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_definicion_requisito_tenant ON modulo1.definicion_requisito (tenant_id, activa)")

    op.execute(
        """
        CREATE TABLE modulo1.legajo (
            legajo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            sujeto_id TEXT NOT NULL,
            tipo_sujeto TEXT NOT NULL CHECK (tipo_sujeto IN ('empresa', 'persona', 'vehiculo', 'equipo')),
            identificador_natural TEXT NOT NULL,
            dado_de_baja_en TIMESTAMPTZ,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_legajo_sujeto UNIQUE (tenant_id, sujeto_id, tipo_sujeto)
        )
        """
    )
    op.execute("CREATE INDEX ix_legajo_tenant ON modulo1.legajo (tenant_id, tipo_sujeto)")

    op.execute(
        """
        CREATE TABLE modulo1.lote_importacion (
            lote_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            origen TEXT NOT NULL CHECK (origen IN ('planilla', 'drive')),
            entidad TEXT NOT NULL CHECK (entidad IN ('legajos', 'oc')),
            filas_totales INTEGER NOT NULL,
            filas_aceptadas INTEGER NOT NULL,
            filas_rechazadas INTEGER NOT NULL,
            detalle_filas_rechazadas JSONB NOT NULL DEFAULT '[]',
            estado TEXT NOT NULL DEFAULT 'aplicado' CHECK (estado IN ('aplicado', 'revertido')),
            hash_archivo TEXT,
            fecha TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_filas_suman CHECK (filas_aceptadas + filas_rechazadas = filas_totales)
        )
        """
    )
    op.execute("CREATE INDEX ix_lote_importacion_tenant ON modulo1.lote_importacion (tenant_id, entidad)")

    op.execute(
        """
        CREATE TABLE modulo1.documento (
            documento_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            sujeto_id TEXT NOT NULL,
            requisito_definicion_id UUID REFERENCES modulo1.definicion_requisito(requisito_definicion_id),
            numero TEXT,
            vigente_desde DATE NOT NULL,
            vigente_hasta DATE NOT NULL,
            estado_confirmacion TEXT NOT NULL DEFAULT 'declarado' CHECK (estado_confirmacion IN ('declarado', 'verificado', 'confirmado_en_fuente')),
            estado_version TEXT NOT NULL DEFAULT 'vigente' CHECK (estado_version IN ('vigente', 'sucedida', 'revertida_por_lote', 'rechazada')),
            origen_propuesta BOOLEAN NOT NULL DEFAULT false,
            version INTEGER NOT NULL DEFAULT 1,
            origen TEXT NOT NULL CHECK (origen IN ('planilla', 'carga_manual', 'drive')),
            confianza_extraccion TEXT CHECK (confianza_extraccion IN ('alta', 'media', 'baja')),
            clave_storage TEXT,
            checksum_archivo TEXT,
            lote_id UUID REFERENCES modulo1.lote_importacion(lote_id),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_vigencia_documento CHECK (vigente_desde <= vigente_hasta)
        )
        """
    )
    op.execute("CREATE INDEX ix_documento_tenant_sujeto ON modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id)")
    # A lo sumo un Documento vigente por (sujeto, requisito) — 2.2 de especificacion.md.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_documento_vigente
        ON modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id)
        WHERE estado_version = 'vigente' AND requisito_definicion_id IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE modulo1.acreditacion_competencia (
            acreditacion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            persona_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL REFERENCES modulo1.definicion_requisito(requisito_definicion_id),
            vigente_desde DATE NOT NULL,
            vigente_hasta DATE NOT NULL,
            estado_confirmacion TEXT NOT NULL DEFAULT 'declarado' CHECK (estado_confirmacion IN ('declarado', 'verificado', 'confirmado_en_fuente')),
            evidencias UUID[] NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_vigencia_acreditacion CHECK (vigente_desde <= vigente_hasta),
            CONSTRAINT ck_evidencias_no_vacio CHECK (array_length(evidencias, 1) > 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_acreditacion_tenant_persona ON modulo1.acreditacion_competencia (tenant_id, persona_id, requisito_definicion_id)")

    op.execute(
        """
        CREATE TABLE modulo1.induccion (
            induccion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            persona_id TEXT NOT NULL,
            locacion_id UUID NOT NULL,
            requisito_definicion_id UUID NOT NULL REFERENCES modulo1.definicion_requisito(requisito_definicion_id),
            vigente_desde DATE NOT NULL,
            vigente_hasta DATE NOT NULL,
            estado_confirmacion TEXT NOT NULL DEFAULT 'declarado' CHECK (estado_confirmacion IN ('declarado', 'verificado', 'confirmado_en_fuente')),
            evidencia UUID NOT NULL REFERENCES modulo1.documento(documento_id),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_vigencia_induccion CHECK (vigente_desde <= vigente_hasta)
        )
        """
    )
    op.execute("CREATE INDEX ix_induccion_tenant_persona ON modulo1.induccion (tenant_id, persona_id, requisito_definicion_id)")

    op.execute(
        """
        CREATE TABLE modulo1.matriz_requisitos (
            matriz_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            cliente_id UUID NOT NULL,
            locacion_id UUID NOT NULL,
            tipo_servicio_id UUID NOT NULL,
            version INTEGER NOT NULL,
            vigente_desde DATE NOT NULL,
            vigente_hasta DATE,
            fuente TEXT,
            archivo_de_respaldo TEXT,
            autor TEXT,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_matriz_clave_version UNIQUE (tenant_id, cliente_id, locacion_id, tipo_servicio_id, version)
        )
        """
    )
    op.execute("CREATE INDEX ix_matriz_tenant_clave ON modulo1.matriz_requisitos (tenant_id, cliente_id, locacion_id, tipo_servicio_id, vigente_desde)")

    op.execute(
        """
        CREATE TABLE modulo1.linea_requisito (
            matriz_version_id UUID NOT NULL REFERENCES modulo1.matriz_requisitos(matriz_version_id) ON DELETE CASCADE,
            requisito_definicion_id UUID NOT NULL REFERENCES modulo1.definicion_requisito(requisito_definicion_id),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            clasificacion TEXT NOT NULL CHECK (clasificacion IN ('bloqueante_duro', 'excepcionable')),
            bloqueante_durante_ejecucion BOOLEAN NOT NULL,
            PRIMARY KEY (matriz_version_id, requisito_definicion_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE modulo1.requisito_particular (
            requisito_particular_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            commitment_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL REFERENCES modulo1.definicion_requisito(requisito_definicion_id),
            clasificacion TEXT NOT NULL CHECK (clasificacion IN ('bloqueante_duro', 'excepcionable')),
            bloqueante_durante_ejecucion BOOLEAN NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_requisito_particular UNIQUE (tenant_id, commitment_id, requisito_definicion_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE modulo1.custodia_recurso (
            custodia_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            recurso_id TEXT NOT NULL,
            tipo_recurso TEXT NOT NULL CHECK (tipo_recurso IN ('vehiculo', 'equipo')),
            CONSTRAINT uq_custodia_recurso UNIQUE (tenant_id, recurso_id, tipo_recurso)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE modulo1.periodo_custodia (
            periodo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            custodia_id UUID NOT NULL REFERENCES modulo1.custodia_recurso(custodia_id) ON DELETE CASCADE,
            custodio_id TEXT,
            desde DATE NOT NULL,
            hasta DATE,
            estado TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'cerrado', 'corregido')),
            corregido_por UUID REFERENCES modulo1.periodo_custodia(periodo_id),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_hasta_solo_si_no_vigente CHECK (
                (estado = 'vigente' AND hasta IS NULL) OR (estado != 'vigente')
            )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_periodo_custodia_vigente
        ON modulo1.periodo_custodia (custodia_id)
        WHERE estado = 'vigente'
        """
    )

    op.execute(
        """
        CREATE TABLE modulo1.excepcion (
            excepcion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            referencia_evaluacion UUID NOT NULL,
            sujeto_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL REFERENCES modulo1.definicion_requisito(requisito_definicion_id),
            commitment_id TEXT NOT NULL,
            otorgada_por TEXT NOT NULL,
            motivo TEXT NOT NULL,
            vigencia DATE,
            evidencia TEXT,
            estado TEXT NOT NULL DEFAULT 'otorgada' CHECK (estado IN ('otorgada', 'revocada', 'regularizada', 'vencida')),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_excepcion_tenant_sujeto ON modulo1.excepcion (tenant_id, sujeto_id, requisito_definicion_id, commitment_id)")

    op.execute(
        """
        CREATE TABLE modulo1.constancia_cliente (
            constancia_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            sujeto_id TEXT NOT NULL,
            requisito_definicion_id UUID NOT NULL REFERENCES modulo1.definicion_requisito(requisito_definicion_id),
            cliente_id UUID NOT NULL,
            commitment_id TEXT,
            registrada_por TEXT NOT NULL,
            emisor TEXT,
            evidencia TEXT NOT NULL,
            vigencia DATE,
            estado TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'vencida', 'revocada', 'reemplazada')),
            reemplazada_por UUID REFERENCES modulo1.constancia_cliente(constancia_id),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_constancia_tenant_sujeto ON modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id)")

    op.execute(
        """
        CREATE TABLE modulo1.evaluacion_habilitacion (
            referencia_evaluacion UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            commitment_id TEXT NOT NULL,
            veredicto_de_cumplimiento TEXT NOT NULL CHECK (veredicto_de_cumplimiento IN ('habilitado', 'vence_durante_el_trabajo', 'no_habilitado', 'requiere_revision')),
            resultado_de_decision TEXT NOT NULL CHECK (resultado_de_decision IN ('puede_asignarse', 'puede_asignarse_bajo_excepcion', 'no_puede_asignarse')),
            por_sujeto JSONB NOT NULL,
            requisitos_faltantes JSONB NOT NULL DEFAULT '[]',
            version_vista_compromiso TEXT,
            version_matriz JSONB,
            snapshot JSONB NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_excepcion_nunca_verde CHECK (
                resultado_de_decision != 'puede_asignarse_bajo_excepcion'
                OR veredicto_de_cumplimiento IN ('no_habilitado', 'vence_durante_el_trabajo')
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_evaluacion_tenant_commitment ON modulo1.evaluacion_habilitacion (tenant_id, commitment_id, creado_en DESC)")

    # ------------------------------------------------------------------
    # OC standalone (1.12 de modulo1-documentacion-habilitante.md) + vista de
    # compromiso (proyección de Módulo 2, cuando esté integrado).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE modulo1.oc (
            oc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            clave_origen TEXT NOT NULL,
            referencia TEXT,
            cliente_id UUID NOT NULL,
            locacion_id UUID NOT NULL,
            tipo_servicio_id UUID NOT NULL,
            vigencia_desde DATE NOT NULL,
            vigencia_hasta DATE NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'cancelado')),
            lote_id UUID REFERENCES modulo1.lote_importacion(lote_id),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_oc_clave_origen UNIQUE (tenant_id, clave_origen),
            CONSTRAINT ck_vigencia_oc CHECK (vigencia_desde <= vigencia_hasta)
        )
        """
    )
    op.execute("CREATE INDEX ix_oc_tenant_estado ON modulo1.oc (tenant_id, estado, locacion_id)")

    # ------------------------------------------------------------------
    # Infraestructura — 8.2 (idempotencia de ImportarLote ya cubierta por lote_id
    # arriba), 8.3 (outbox + log de eventos), 8.4 (cola a mano), 9.3 (idempotencia de
    # transporte para comandos sueltos).
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE modulo1.idempotency_keys (
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            idempotency_key TEXT NOT NULL,
            resultado JSONB,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            expira_en TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (tenant_id, idempotency_key)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE modulo1.outbox_events (
            evento_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            tipo TEXT NOT NULL CHECK (tipo IN ('HabilitacionRequiereRevaluacion', 'CumplimientoEmpresaAfectado')),
            payload JSONB NOT NULL,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            procesado_en TIMESTAMPTZ,
            intentos INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX ix_outbox_pendientes ON modulo1.outbox_events (creado_en) WHERE procesado_en IS NULL")

    op.execute(
        """
        CREATE TABLE modulo1.event_log (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES modulo1.tenant(tenant_id),
            evento_id UUID NOT NULL DEFAULT gen_random_uuid(),
            tipo TEXT NOT NULL,
            payload JSONB NOT NULL,
            ocurrido_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_event_log_tenant ON modulo1.event_log (tenant_id, ocurrido_en DESC)")

    op.execute(
        """
        CREATE TABLE modulo1.job_queue (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID REFERENCES modulo1.tenant(tenant_id),
            cola TEXT NOT NULL CHECK (cola IN ('drenaje_outbox', 'notificaciones', 'evidencia_qr', 'score_documental', 'validacion_evidencia')),
            payload JSONB NOT NULL,
            disponible_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            tomado_en TIMESTAMPTZ,
            lease_hasta TIMESTAMPTZ,
            intentos INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'en_curso', 'completado', 'fallido')),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # Índice que hace eficiente el SELECT ... FOR UPDATE SKIP LOCKED (8.4) y detecta
    # leases vencidos (la vulnerabilidad documentada del patrón a mano).
    op.execute(
        """
        CREATE INDEX ix_job_queue_disponibles
        ON modulo1.job_queue (cola, disponible_en)
        WHERE estado = 'pendiente'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_job_queue_lease_vencido
        ON modulo1.job_queue (lease_hasta)
        WHERE estado = 'en_curso'
        """
    )

    # ------------------------------------------------------------------
    # RLS: ENABLE + FORCE en toda tabla tenant-scoped, con la misma política.
    # ------------------------------------------------------------------
    tablas_con_rls = [
        "definicion_requisito",
        "legajo",
        "lote_importacion",
        "documento",
        "acreditacion_competencia",
        "induccion",
        "matriz_requisitos",
        "linea_requisito",
        "requisito_particular",
        "custodia_recurso",
        "periodo_custodia",
        "excepcion",
        "constancia_cliente",
        "evaluacion_habilitacion",
        "oc",
        "idempotency_keys",
        "outbox_events",
        "event_log",
        "job_queue",
    ]
    for tabla in tablas_con_rls:
        op.execute(f"ALTER TABLE modulo1.{tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE modulo1.{tabla} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {tabla}_aislamiento ON modulo1.{tabla}
            USING (tenant_id = current_setting('app.current_tenant')::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)
            """
        )
    # job_queue permite tenant_id NULL (jobs de sistema, ej. drenaje que recorre todos
    # los tenants) — la política de arriba los ocultaría; se agrega una excepción.
    op.execute("DROP POLICY job_queue_aislamiento ON modulo1.job_queue")
    op.execute(
        """
        CREATE POLICY job_queue_aislamiento ON modulo1.job_queue
        USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant')::uuid)
        WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant')::uuid)
        """
    )

    # ------------------------------------------------------------------
    # Roles y permisos (8.1, decisiones 1-2 y 4).
    # ------------------------------------------------------------------
    # Los roles modulo1_owner / modulo1_app los crea scripts/crear_roles.sql ANTES de
    # Alembic, con contraseñas provistas por el operador (M-07): acá solo se otorgan
    # permisos sobre un rol que ya existe.
    op.execute("GRANT USAGE ON SCHEMA modulo1 TO modulo1_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA modulo1 TO modulo1_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA modulo1 TO modulo1_app")
    op.execute("GRANT USAGE ON SCHEMA plataforma TO modulo1_app")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA plataforma TO modulo1_app")
    # modulo1_app explícitamente NO tiene BYPASSRLS y no es owner de nada — lo crea
    # este script con el rol owner (DATABASE_URL_MIGRATIONS), así que modulo1_app
    # nunca puede escalar sus propios privilegios.


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS modulo1 CASCADE")
    op.execute("DROP SCHEMA IF EXISTS plataforma CASCADE")
