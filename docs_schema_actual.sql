\restrict vgMk3aAcYjirhjTPEeRIJf0rotvmH4O61ZuSi5iWK39DIYAqwhzgFdjoS5Z9KKL
CREATE SCHEMA modulo1;
CREATE SCHEMA plataforma;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';
CREATE TABLE modulo1.acreditacion_competencia (
    acreditacion_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    persona_id text NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date NOT NULL,
    estado_confirmacion text DEFAULT 'declarado'::text NOT NULL,
    evidencias uuid[] NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT acreditacion_competencia_estado_confirmacion_check CHECK ((estado_confirmacion = ANY (ARRAY['declarado'::text, 'verificado'::text, 'confirmado_en_fuente'::text]))),
    CONSTRAINT ck_evidencias_no_vacio CHECK ((array_length(evidencias, 1) > 0)),
    CONSTRAINT ck_vigencia_acreditacion CHECK ((vigente_desde <= vigente_hasta))
);
ALTER TABLE ONLY modulo1.acreditacion_competencia FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.constancia_cliente (
    constancia_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    sujeto_id text NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    commitment_id text,
    registrada_por text NOT NULL,
    emisor text,
    evidencia text NOT NULL,
    vigencia date,
    estado text DEFAULT 'vigente'::text NOT NULL,
    reemplazada_por uuid,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT constancia_cliente_estado_check CHECK ((estado = ANY (ARRAY['vigente'::text, 'vencida'::text, 'revocada'::text, 'reemplazada'::text])))
);
ALTER TABLE ONLY modulo1.constancia_cliente FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.custodia_recurso (
    custodia_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    recurso_id text NOT NULL,
    tipo_recurso text NOT NULL,
    CONSTRAINT custodia_recurso_tipo_recurso_check CHECK ((tipo_recurso = ANY (ARRAY['vehiculo'::text, 'equipo'::text])))
);
ALTER TABLE ONLY modulo1.custodia_recurso FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.definicion_requisito (
    requisito_definicion_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    nombre text NOT NULL,
    categoria text NOT NULL,
    tipo_sujeto_aplicable text NOT NULL,
    locacion_id uuid,
    activa boolean DEFAULT true NOT NULL,
    definicion_global_id uuid,
    plazo_retencion_archivo interval,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT definicion_requisito_categoria_check CHECK ((categoria = ANY (ARRAY['documento'::text, 'competencia'::text, 'induccion'::text]))),
    CONSTRAINT definicion_requisito_tipo_sujeto_aplicable_check CHECK ((tipo_sujeto_aplicable = ANY (ARRAY['empresa'::text, 'persona'::text, 'vehiculo'::text, 'equipo'::text]))),
    CONSTRAINT induccion_requiere_locacion CHECK ((((categoria = 'induccion'::text) AND (locacion_id IS NOT NULL)) OR ((categoria <> 'induccion'::text) AND (locacion_id IS NULL))))
);
ALTER TABLE ONLY modulo1.definicion_requisito FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.documento (
    documento_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    sujeto_id text NOT NULL,
    requisito_definicion_id uuid,
    numero text,
    vigente_desde date NOT NULL,
    vigente_hasta date NOT NULL,
    estado_confirmacion text DEFAULT 'declarado'::text NOT NULL,
    estado_version text DEFAULT 'vigente'::text NOT NULL,
    origen_propuesta boolean DEFAULT false NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    origen text NOT NULL,
    confianza_extraccion text,
    clave_storage text,
    checksum_archivo text,
    lote_id uuid,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vigencia_documento CHECK ((vigente_desde <= vigente_hasta)),
    CONSTRAINT documento_confianza_extraccion_check CHECK ((confianza_extraccion = ANY (ARRAY['alta'::text, 'media'::text, 'baja'::text]))),
    CONSTRAINT documento_estado_confirmacion_check CHECK ((estado_confirmacion = ANY (ARRAY['declarado'::text, 'verificado'::text, 'confirmado_en_fuente'::text]))),
    CONSTRAINT documento_estado_version_check CHECK ((estado_version = ANY (ARRAY['vigente'::text, 'sucedida'::text, 'revertida_por_lote'::text, 'rechazada'::text]))),
    CONSTRAINT documento_origen_check CHECK ((origen = ANY (ARRAY['planilla'::text, 'carga_manual'::text, 'drive'::text])))
);
ALTER TABLE ONLY modulo1.documento FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.evaluacion_habilitacion (
    referencia_evaluacion uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    commitment_id text NOT NULL,
    veredicto_de_cumplimiento text NOT NULL,
    resultado_de_decision text NOT NULL,
    por_sujeto jsonb NOT NULL,
    requisitos_faltantes jsonb DEFAULT '[]'::jsonb NOT NULL,
    version_vista_compromiso text,
    version_matriz jsonb,
    snapshot jsonb NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_excepcion_nunca_verde CHECK (((resultado_de_decision <> 'puede_asignarse_bajo_excepcion'::text) OR (veredicto_de_cumplimiento = ANY (ARRAY['no_habilitado'::text, 'vence_durante_el_trabajo'::text])))),
    CONSTRAINT evaluacion_habilitacion_resultado_de_decision_check CHECK ((resultado_de_decision = ANY (ARRAY['puede_asignarse'::text, 'puede_asignarse_bajo_excepcion'::text, 'no_puede_asignarse'::text]))),
    CONSTRAINT evaluacion_habilitacion_veredicto_de_cumplimiento_check CHECK ((veredicto_de_cumplimiento = ANY (ARRAY['habilitado'::text, 'vence_durante_el_trabajo'::text, 'no_habilitado'::text, 'requiere_revision'::text])))
);
ALTER TABLE ONLY modulo1.evaluacion_habilitacion FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.event_log (
    id bigint NOT NULL,
    tenant_id uuid NOT NULL,
    evento_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tipo text NOT NULL,
    payload jsonb NOT NULL,
    ocurrido_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.event_log FORCE ROW LEVEL SECURITY;
CREATE SEQUENCE modulo1.event_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE modulo1.event_log_id_seq OWNED BY modulo1.event_log.id;
CREATE TABLE modulo1.excepcion (
    excepcion_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    referencia_evaluacion uuid NOT NULL,
    sujeto_id text NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    commitment_id text NOT NULL,
    otorgada_por text NOT NULL,
    motivo text NOT NULL,
    vigencia date,
    evidencia text,
    estado text DEFAULT 'otorgada'::text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT excepcion_estado_check CHECK ((estado = ANY (ARRAY['otorgada'::text, 'revocada'::text, 'regularizada'::text, 'vencida'::text])))
);
ALTER TABLE ONLY modulo1.excepcion FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.idempotency_keys (
    tenant_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    resultado jsonb,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    expira_en timestamp with time zone NOT NULL
);
ALTER TABLE ONLY modulo1.idempotency_keys FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.induccion (
    induccion_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    persona_id text NOT NULL,
    locacion_id uuid NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date NOT NULL,
    estado_confirmacion text DEFAULT 'declarado'::text NOT NULL,
    evidencia uuid NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vigencia_induccion CHECK ((vigente_desde <= vigente_hasta)),
    CONSTRAINT induccion_estado_confirmacion_check CHECK ((estado_confirmacion = ANY (ARRAY['declarado'::text, 'verificado'::text, 'confirmado_en_fuente'::text])))
);
ALTER TABLE ONLY modulo1.induccion FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.job_queue (
    id bigint NOT NULL,
    tenant_id uuid,
    cola text NOT NULL,
    payload jsonb NOT NULL,
    disponible_en timestamp with time zone DEFAULT now() NOT NULL,
    tomado_en timestamp with time zone,
    lease_hasta timestamp with time zone,
    intentos integer DEFAULT 0 NOT NULL,
    estado text DEFAULT 'pendiente'::text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_queue_cola_check CHECK ((cola = ANY (ARRAY['drenaje_outbox'::text, 'notificaciones'::text, 'evidencia_qr'::text, 'score_documental'::text, 'validacion_evidencia'::text]))),
    CONSTRAINT job_queue_estado_check CHECK ((estado = ANY (ARRAY['pendiente'::text, 'en_curso'::text, 'completado'::text, 'fallido'::text])))
);
ALTER TABLE ONLY modulo1.job_queue FORCE ROW LEVEL SECURITY;
CREATE SEQUENCE modulo1.job_queue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE modulo1.job_queue_id_seq OWNED BY modulo1.job_queue.id;
CREATE TABLE modulo1.legajo (
    legajo_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    sujeto_id text NOT NULL,
    tipo_sujeto text NOT NULL,
    identificador_natural text NOT NULL,
    dado_de_baja_en timestamp with time zone,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT legajo_tipo_sujeto_check CHECK ((tipo_sujeto = ANY (ARRAY['empresa'::text, 'persona'::text, 'vehiculo'::text, 'equipo'::text])))
);
ALTER TABLE ONLY modulo1.legajo FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.linea_requisito (
    matriz_version_id uuid NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    clasificacion text NOT NULL,
    bloqueante_durante_ejecucion boolean NOT NULL,
    CONSTRAINT linea_requisito_clasificacion_check CHECK ((clasificacion = ANY (ARRAY['bloqueante_duro'::text, 'excepcionable'::text])))
);
ALTER TABLE ONLY modulo1.linea_requisito FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.lote_importacion (
    lote_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    origen text NOT NULL,
    entidad text NOT NULL,
    filas_totales integer NOT NULL,
    filas_aceptadas integer NOT NULL,
    filas_rechazadas integer NOT NULL,
    detalle_filas_rechazadas jsonb DEFAULT '[]'::jsonb NOT NULL,
    estado text DEFAULT 'aplicado'::text NOT NULL,
    hash_archivo text,
    fecha timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_filas_suman CHECK (((filas_aceptadas + filas_rechazadas) = filas_totales)),
    CONSTRAINT lote_importacion_entidad_check CHECK ((entidad = ANY (ARRAY['legajos'::text, 'oc'::text]))),
    CONSTRAINT lote_importacion_estado_check CHECK ((estado = ANY (ARRAY['aplicado'::text, 'revertido'::text]))),
    CONSTRAINT lote_importacion_origen_check CHECK ((origen = ANY (ARRAY['planilla'::text, 'drive'::text])))
);
ALTER TABLE ONLY modulo1.lote_importacion FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.matriz_requisitos (
    matriz_version_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    locacion_id uuid NOT NULL,
    tipo_servicio_id uuid NOT NULL,
    version integer NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,
    fuente text,
    archivo_de_respaldo text,
    autor text,
    creado_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.matriz_requisitos FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.oc (
    oc_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    clave_origen text NOT NULL,
    referencia text,
    cliente_id uuid NOT NULL,
    locacion_id uuid NOT NULL,
    tipo_servicio_id uuid NOT NULL,
    vigencia_desde date NOT NULL,
    vigencia_hasta date NOT NULL,
    estado text DEFAULT 'activo'::text NOT NULL,
    lote_id uuid,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    actualizado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vigencia_oc CHECK ((vigencia_desde <= vigencia_hasta)),
    CONSTRAINT oc_estado_check CHECK ((estado = ANY (ARRAY['activo'::text, 'cancelado'::text])))
);
ALTER TABLE ONLY modulo1.oc FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.outbox_events (
    evento_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    tipo text NOT NULL,
    payload jsonb NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    procesado_en timestamp with time zone,
    intentos integer DEFAULT 0 NOT NULL,
    CONSTRAINT outbox_events_tipo_check CHECK ((tipo = ANY (ARRAY['HabilitacionRequiereRevaluacion'::text, 'CumplimientoEmpresaAfectado'::text])))
);
ALTER TABLE ONLY modulo1.outbox_events FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.periodo_custodia (
    periodo_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    custodia_id uuid NOT NULL,
    custodio_id text,
    desde date NOT NULL,
    hasta date,
    estado text DEFAULT 'vigente'::text NOT NULL,
    corregido_por uuid,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_hasta_solo_si_no_vigente CHECK ((((estado = 'vigente'::text) AND (hasta IS NULL)) OR (estado <> 'vigente'::text))),
    CONSTRAINT periodo_custodia_estado_check CHECK ((estado = ANY (ARRAY['vigente'::text, 'cerrado'::text, 'corregido'::text])))
);
ALTER TABLE ONLY modulo1.periodo_custodia FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.requisito_particular (
    requisito_particular_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    commitment_id text NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    clasificacion text NOT NULL,
    bloqueante_durante_ejecucion boolean NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT requisito_particular_clasificacion_check CHECK ((clasificacion = ANY (ARRAY['bloqueante_duro'::text, 'excepcionable'::text])))
);
ALTER TABLE ONLY modulo1.requisito_particular FORCE ROW LEVEL SECURITY;
CREATE TABLE modulo1.tenant (
    tenant_id uuid DEFAULT gen_random_uuid() NOT NULL,
    nombre text NOT NULL,
    zona_horaria text DEFAULT 'America/Argentina/Buenos_Aires'::text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.tenant FORCE ROW LEVEL SECURITY;
CREATE TABLE plataforma.definicion_requisito_global (
    definicion_global_id uuid DEFAULT gen_random_uuid() NOT NULL,
    nombre text NOT NULL,
    categoria text NOT NULL,
    tipo_sujeto_aplicable text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    activa boolean DEFAULT true NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT definicion_requisito_global_categoria_check CHECK ((categoria = ANY (ARRAY['documento'::text, 'competencia'::text, 'induccion'::text]))),
    CONSTRAINT definicion_requisito_global_tipo_sujeto_aplicable_check CHECK ((tipo_sujeto_aplicable = ANY (ARRAY['empresa'::text, 'persona'::text, 'vehiculo'::text, 'equipo'::text])))
);
CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);
ALTER TABLE ONLY modulo1.event_log ALTER COLUMN id SET DEFAULT nextval('modulo1.event_log_id_seq'::regclass);
ALTER TABLE ONLY modulo1.job_queue ALTER COLUMN id SET DEFAULT nextval('modulo1.job_queue_id_seq'::regclass);
ALTER TABLE ONLY modulo1.acreditacion_competencia
    ADD CONSTRAINT acreditacion_competencia_pkey PRIMARY KEY (acreditacion_id);
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT constancia_cliente_pkey PRIMARY KEY (constancia_id);
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT custodia_recurso_pkey PRIMARY KEY (custodia_id);
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT definicion_requisito_pkey PRIMARY KEY (requisito_definicion_id);
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT documento_pkey PRIMARY KEY (documento_id);
ALTER TABLE ONLY modulo1.evaluacion_habilitacion
    ADD CONSTRAINT evaluacion_habilitacion_pkey PRIMARY KEY (referencia_evaluacion);
ALTER TABLE ONLY modulo1.event_log
    ADD CONSTRAINT event_log_pkey PRIMARY KEY (id);
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT excepcion_pkey PRIMARY KEY (excepcion_id);
ALTER TABLE ONLY modulo1.idempotency_keys
    ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (tenant_id, idempotency_key);
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT induccion_pkey PRIMARY KEY (induccion_id);
ALTER TABLE ONLY modulo1.job_queue
    ADD CONSTRAINT job_queue_pkey PRIMARY KEY (id);
ALTER TABLE ONLY modulo1.legajo
    ADD CONSTRAINT legajo_pkey PRIMARY KEY (legajo_id);
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT linea_requisito_pkey PRIMARY KEY (matriz_version_id, requisito_definicion_id);
ALTER TABLE ONLY modulo1.lote_importacion
    ADD CONSTRAINT lote_importacion_pkey PRIMARY KEY (lote_id);
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT matriz_requisitos_pkey PRIMARY KEY (matriz_version_id);
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT oc_pkey PRIMARY KEY (oc_id);
ALTER TABLE ONLY modulo1.outbox_events
    ADD CONSTRAINT outbox_events_pkey PRIMARY KEY (evento_id);
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT periodo_custodia_pkey PRIMARY KEY (periodo_id);
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT requisito_particular_pkey PRIMARY KEY (requisito_particular_id);
ALTER TABLE ONLY modulo1.tenant
    ADD CONSTRAINT tenant_pkey PRIMARY KEY (tenant_id);
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT uq_custodia_recurso UNIQUE (tenant_id, recurso_id, tipo_recurso);
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT uq_definicion_requisito UNIQUE (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id);
ALTER TABLE ONLY modulo1.legajo
    ADD CONSTRAINT uq_legajo_sujeto UNIQUE (tenant_id, sujeto_id, tipo_sujeto);
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT uq_matriz_clave_version UNIQUE (tenant_id, cliente_id, locacion_id, tipo_servicio_id, version);
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT uq_oc_clave_origen UNIQUE (tenant_id, clave_origen);
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT uq_requisito_particular UNIQUE (tenant_id, commitment_id, requisito_definicion_id);
ALTER TABLE ONLY plataforma.definicion_requisito_global
    ADD CONSTRAINT definicion_requisito_global_pkey PRIMARY KEY (definicion_global_id);
ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);
CREATE INDEX ix_acreditacion_tenant_persona ON modulo1.acreditacion_competencia USING btree (tenant_id, persona_id, requisito_definicion_id);
CREATE INDEX ix_constancia_tenant_sujeto ON modulo1.constancia_cliente USING btree (tenant_id, sujeto_id, requisito_definicion_id, cliente_id);
CREATE INDEX ix_definicion_requisito_tenant ON modulo1.definicion_requisito USING btree (tenant_id, activa);
CREATE INDEX ix_documento_tenant_sujeto ON modulo1.documento USING btree (tenant_id, sujeto_id, requisito_definicion_id);
CREATE INDEX ix_evaluacion_tenant_commitment ON modulo1.evaluacion_habilitacion USING btree (tenant_id, commitment_id, creado_en DESC);
CREATE INDEX ix_event_log_tenant ON modulo1.event_log USING btree (tenant_id, ocurrido_en DESC);
CREATE INDEX ix_excepcion_tenant_sujeto ON modulo1.excepcion USING btree (tenant_id, sujeto_id, requisito_definicion_id, commitment_id);
CREATE INDEX ix_induccion_tenant_persona ON modulo1.induccion USING btree (tenant_id, persona_id, requisito_definicion_id);
CREATE INDEX ix_job_queue_disponibles ON modulo1.job_queue USING btree (cola, disponible_en) WHERE (estado = 'pendiente'::text);
CREATE INDEX ix_job_queue_lease_vencido ON modulo1.job_queue USING btree (lease_hasta) WHERE (estado = 'en_curso'::text);
CREATE INDEX ix_legajo_tenant ON modulo1.legajo USING btree (tenant_id, tipo_sujeto);
CREATE INDEX ix_lote_importacion_tenant ON modulo1.lote_importacion USING btree (tenant_id, entidad);
CREATE INDEX ix_matriz_tenant_clave ON modulo1.matriz_requisitos USING btree (tenant_id, cliente_id, locacion_id, tipo_servicio_id, vigente_desde);
CREATE INDEX ix_oc_tenant_estado ON modulo1.oc USING btree (tenant_id, estado, locacion_id);
CREATE INDEX ix_outbox_pendientes ON modulo1.outbox_events USING btree (creado_en) WHERE (procesado_en IS NULL);
CREATE UNIQUE INDEX uq_documento_vigente ON modulo1.documento USING btree (tenant_id, sujeto_id, requisito_definicion_id) WHERE ((estado_version = 'vigente'::text) AND (requisito_definicion_id IS NOT NULL));
CREATE UNIQUE INDEX uq_periodo_custodia_vigente ON modulo1.periodo_custodia USING btree (custodia_id) WHERE (estado = 'vigente'::text);
ALTER TABLE ONLY modulo1.acreditacion_competencia
    ADD CONSTRAINT acreditacion_competencia_requisito_definicion_id_fkey FOREIGN KEY (requisito_definicion_id) REFERENCES modulo1.definicion_requisito(requisito_definicion_id);
ALTER TABLE ONLY modulo1.acreditacion_competencia
    ADD CONSTRAINT acreditacion_competencia_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT constancia_cliente_reemplazada_por_fkey FOREIGN KEY (reemplazada_por) REFERENCES modulo1.constancia_cliente(constancia_id);
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT constancia_cliente_requisito_definicion_id_fkey FOREIGN KEY (requisito_definicion_id) REFERENCES modulo1.definicion_requisito(requisito_definicion_id);
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT constancia_cliente_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT custodia_recurso_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT definicion_requisito_definicion_global_id_fkey FOREIGN KEY (definicion_global_id) REFERENCES plataforma.definicion_requisito_global(definicion_global_id);
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT definicion_requisito_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT documento_lote_id_fkey FOREIGN KEY (lote_id) REFERENCES modulo1.lote_importacion(lote_id);
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT documento_requisito_definicion_id_fkey FOREIGN KEY (requisito_definicion_id) REFERENCES modulo1.definicion_requisito(requisito_definicion_id);
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT documento_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.evaluacion_habilitacion
    ADD CONSTRAINT evaluacion_habilitacion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.event_log
    ADD CONSTRAINT event_log_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT excepcion_requisito_definicion_id_fkey FOREIGN KEY (requisito_definicion_id) REFERENCES modulo1.definicion_requisito(requisito_definicion_id);
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT excepcion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.idempotency_keys
    ADD CONSTRAINT idempotency_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT induccion_evidencia_fkey FOREIGN KEY (evidencia) REFERENCES modulo1.documento(documento_id);
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT induccion_requisito_definicion_id_fkey FOREIGN KEY (requisito_definicion_id) REFERENCES modulo1.definicion_requisito(requisito_definicion_id);
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT induccion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.job_queue
    ADD CONSTRAINT job_queue_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.legajo
    ADD CONSTRAINT legajo_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT linea_requisito_matriz_version_id_fkey FOREIGN KEY (matriz_version_id) REFERENCES modulo1.matriz_requisitos(matriz_version_id) ON DELETE CASCADE;
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT linea_requisito_requisito_definicion_id_fkey FOREIGN KEY (requisito_definicion_id) REFERENCES modulo1.definicion_requisito(requisito_definicion_id);
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT linea_requisito_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.lote_importacion
    ADD CONSTRAINT lote_importacion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT matriz_requisitos_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT oc_lote_id_fkey FOREIGN KEY (lote_id) REFERENCES modulo1.lote_importacion(lote_id);
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT oc_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.outbox_events
    ADD CONSTRAINT outbox_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT periodo_custodia_corregido_por_fkey FOREIGN KEY (corregido_por) REFERENCES modulo1.periodo_custodia(periodo_id);
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT periodo_custodia_custodia_id_fkey FOREIGN KEY (custodia_id) REFERENCES modulo1.custodia_recurso(custodia_id) ON DELETE CASCADE;
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT periodo_custodia_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT requisito_particular_requisito_definicion_id_fkey FOREIGN KEY (requisito_definicion_id) REFERENCES modulo1.definicion_requisito(requisito_definicion_id);
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT requisito_particular_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
ALTER TABLE modulo1.acreditacion_competencia ENABLE ROW LEVEL SECURITY;
CREATE POLICY acreditacion_competencia_aislamiento ON modulo1.acreditacion_competencia USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.constancia_cliente ENABLE ROW LEVEL SECURITY;
CREATE POLICY constancia_cliente_aislamiento ON modulo1.constancia_cliente USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.custodia_recurso ENABLE ROW LEVEL SECURITY;
CREATE POLICY custodia_recurso_aislamiento ON modulo1.custodia_recurso USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.definicion_requisito ENABLE ROW LEVEL SECURITY;
CREATE POLICY definicion_requisito_aislamiento ON modulo1.definicion_requisito USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.documento ENABLE ROW LEVEL SECURITY;
CREATE POLICY documento_aislamiento ON modulo1.documento USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.evaluacion_habilitacion ENABLE ROW LEVEL SECURITY;
CREATE POLICY evaluacion_habilitacion_aislamiento ON modulo1.evaluacion_habilitacion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.event_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY event_log_aislamiento ON modulo1.event_log USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.excepcion ENABLE ROW LEVEL SECURITY;
CREATE POLICY excepcion_aislamiento ON modulo1.excepcion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.idempotency_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY idempotency_keys_aislamiento ON modulo1.idempotency_keys USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.induccion ENABLE ROW LEVEL SECURITY;
CREATE POLICY induccion_aislamiento ON modulo1.induccion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.job_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY job_queue_aislamiento ON modulo1.job_queue USING (((tenant_id IS NULL) OR (tenant_id = (current_setting('app.current_tenant'::text))::uuid))) WITH CHECK (((tenant_id IS NULL) OR (tenant_id = (current_setting('app.current_tenant'::text))::uuid)));
ALTER TABLE modulo1.legajo ENABLE ROW LEVEL SECURITY;
CREATE POLICY legajo_aislamiento ON modulo1.legajo USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.linea_requisito ENABLE ROW LEVEL SECURITY;
CREATE POLICY linea_requisito_aislamiento ON modulo1.linea_requisito USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.lote_importacion ENABLE ROW LEVEL SECURITY;
CREATE POLICY lote_importacion_aislamiento ON modulo1.lote_importacion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.matriz_requisitos ENABLE ROW LEVEL SECURITY;
CREATE POLICY matriz_requisitos_aislamiento ON modulo1.matriz_requisitos USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.oc ENABLE ROW LEVEL SECURITY;
CREATE POLICY oc_aislamiento ON modulo1.oc USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.outbox_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY outbox_events_aislamiento ON modulo1.outbox_events USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.periodo_custodia ENABLE ROW LEVEL SECURITY;
CREATE POLICY periodo_custodia_aislamiento ON modulo1.periodo_custodia USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.requisito_particular ENABLE ROW LEVEL SECURITY;
CREATE POLICY requisito_particular_aislamiento ON modulo1.requisito_particular USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
ALTER TABLE modulo1.tenant ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_aislamiento ON modulo1.tenant USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
\unrestrict vgMk3aAcYjirhjTPEeRIJf0rotvmH4O61ZuSi5iWK39DIYAqwhzgFdjoS5Z9KKL
