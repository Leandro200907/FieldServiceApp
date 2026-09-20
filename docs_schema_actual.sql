-- docs_schema_actual.sql — esquema de Módulo 1 generado por scripts/generar_schema.py
-- head: 0016_plantillas_globales
-- Base creada desde cero (scripts/crear_roles.sql → scripts/crear_base.sql → alembic upgrade head),
-- pg_dump --schema-only --no-owner --no-privileges. Sin datos ni credenciales. No editar a mano.

-- PostgreSQL database dump
-- Name: modulo1; Type: SCHEMA; Schema: -; Owner: -
CREATE SCHEMA modulo1;
-- Name: plataforma; Type: SCHEMA; Schema: -; Owner: -
CREATE SCHEMA plataforma;
-- Name: listar_tenants(); Type: FUNCTION; Schema: modulo1; Owner: -
CREATE FUNCTION modulo1.listar_tenants() RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER
    AS $$
            SELECT tenant_id FROM modulo1.tenant ORDER BY creado_en, tenant_id
        $$;
-- Name: resolver_tenant_por_slug(text); Type: FUNCTION; Schema: modulo1; Owner: -
CREATE FUNCTION modulo1.resolver_tenant_por_slug(p_slug text) RETURNS uuid
    LANGUAGE sql STABLE SECURITY DEFINER
    AS $$
            SELECT tenant_id FROM modulo1.tenant_slug WHERE slug = p_slug
        $$;
-- Name: sincronizar_tenant_slug(); Type: FUNCTION; Schema: modulo1; Owner: -
CREATE FUNCTION modulo1.sincronizar_tenant_slug() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
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
        $$;
-- Name: acreditacion_competencia; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: asignacion_supervisor; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.asignacion_supervisor (
    asignacion_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    sujeto_id text NOT NULL,
    supervisor_usuario_id uuid NOT NULL,
    desde date NOT NULL,
    hasta date,
    estado text DEFAULT 'vigente'::text NOT NULL,
    asignada_por text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT asignacion_supervisor_estado_check CHECK ((estado = ANY (ARRAY['vigente'::text, 'cerrada'::text]))),
    CONSTRAINT ck_asignacion_hasta CHECK ((((estado = 'vigente'::text) AND (hasta IS NULL)) OR (estado <> 'vigente'::text)))
);
ALTER TABLE ONLY modulo1.asignacion_supervisor FORCE ROW LEVEL SECURITY;
-- Name: aviso_incumplimiento_empresa; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.aviso_incumplimiento_empresa (
    aviso_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    estado text DEFAULT 'abierto'::text NOT NULL,
    desde date NOT NULL,
    abierto_en timestamp with time zone DEFAULT now() NOT NULL,
    regularizado_en timestamp with time zone,
    CONSTRAINT aviso_incumplimiento_empresa_estado_check CHECK ((estado = ANY (ARRAY['abierto'::text, 'regularizado'::text]))),
    CONSTRAINT ck_aie_cierre CHECK ((((estado = 'abierto'::text) AND (regularizado_en IS NULL)) OR ((estado = 'regularizado'::text) AND (regularizado_en IS NOT NULL))))
);
ALTER TABLE ONLY modulo1.aviso_incumplimiento_empresa FORCE ROW LEVEL SECURITY;
-- Name: aviso_incumplimiento_empresa_causa; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.aviso_incumplimiento_empresa_causa (
    causa_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    aviso_id uuid NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    estado text DEFAULT 'activa'::text NOT NULL,
    desde date NOT NULL,
    registrada_en timestamp with time zone DEFAULT now() NOT NULL,
    regularizada_en timestamp with time zone,
    CONSTRAINT aviso_incumplimiento_empresa_causa_estado_check CHECK ((estado = ANY (ARRAY['activa'::text, 'regularizada'::text]))),
    CONSTRAINT ck_aiec_cierre CHECK ((((estado = 'activa'::text) AND (regularizada_en IS NULL)) OR ((estado = 'regularizada'::text) AND (regularizada_en IS NOT NULL))))
);
ALTER TABLE ONLY modulo1.aviso_incumplimiento_empresa_causa FORCE ROW LEVEL SECURITY;
-- Name: aviso_revaluacion; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.aviso_revaluacion (
    aviso_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    referencia_evaluacion uuid NOT NULL,
    commitment_id text NOT NULL,
    estado text DEFAULT 'abierto'::text NOT NULL,
    abierto_en timestamp with time zone DEFAULT now() NOT NULL,
    cerrado_en timestamp with time zone,
    cerrado_por_referencia uuid,
    CONSTRAINT aviso_revaluacion_estado_check CHECK ((estado = ANY (ARRAY['abierto'::text, 'cerrado'::text]))),
    CONSTRAINT ck_aviso_cierre CHECK ((((estado = 'abierto'::text) AND (cerrado_en IS NULL)) OR ((estado = 'cerrado'::text) AND (cerrado_en IS NOT NULL))))
);
ALTER TABLE ONLY modulo1.aviso_revaluacion FORCE ROW LEVEL SECURITY;
-- Name: aviso_revaluacion_causa; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.aviso_revaluacion_causa (
    tenant_id uuid NOT NULL,
    aviso_id uuid NOT NULL,
    evento_id uuid NOT NULL,
    tipo_evento text NOT NULL,
    entidad_tipo text NOT NULL,
    entidad_id text NOT NULL,
    registrada_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.aviso_revaluacion_causa FORCE ROW LEVEL SECURITY;
-- Name: constancia_cliente; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: custodia_recurso; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.custodia_recurso (
    custodia_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    recurso_id text NOT NULL,
    tipo_recurso text NOT NULL,
    CONSTRAINT custodia_recurso_tipo_recurso_check CHECK ((tipo_recurso = ANY (ARRAY['vehiculo'::text, 'equipo'::text])))
);
ALTER TABLE ONLY modulo1.custodia_recurso FORCE ROW LEVEL SECURITY;
-- Name: definicion_requisito; Type: TABLE; Schema: modulo1; Owner: -
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
    copiada_de_version integer,
    CONSTRAINT ck_definicion_copia_coherente CHECK ((((definicion_global_id IS NULL) AND (copiada_de_version IS NULL)) OR ((definicion_global_id IS NOT NULL) AND (copiada_de_version IS NOT NULL)))),
    CONSTRAINT definicion_requisito_categoria_check CHECK ((categoria = ANY (ARRAY['documento'::text, 'competencia'::text, 'induccion'::text]))),
    CONSTRAINT definicion_requisito_tipo_sujeto_aplicable_check CHECK ((tipo_sujeto_aplicable = ANY (ARRAY['empresa'::text, 'persona'::text, 'vehiculo'::text, 'equipo'::text]))),
    CONSTRAINT induccion_requiere_locacion CHECK ((((categoria = 'induccion'::text) AND (locacion_id IS NOT NULL)) OR ((categoria <> 'induccion'::text) AND (locacion_id IS NULL))))
);
ALTER TABLE ONLY modulo1.definicion_requisito FORCE ROW LEVEL SECURITY;
-- Name: documento; Type: TABLE; Schema: modulo1; Owner: -
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
    sucede_a uuid,
    archivo_estado text DEFAULT 'sin_archivo'::text NOT NULL,
    archivo_content_type text,
    archivo_bytes bigint,
    archivo_purgado_en timestamp with time zone,
    CONSTRAINT ck_archivo_clave_del_documento CHECK (((clave_storage IS NULL) OR (clave_storage ~~ ((((tenant_id)::text || '/'::text) || (documento_id)::text) || '/%'::text)))),
    CONSTRAINT ck_archivo_clave_segun_estado CHECK ((((archivo_estado = ANY (ARRAY['sin_archivo'::text, 'purgado'::text])) AND (clave_storage IS NULL)) OR ((archivo_estado <> ALL (ARRAY['sin_archivo'::text, 'purgado'::text])) AND (clave_storage IS NOT NULL)))),
    CONSTRAINT ck_archivo_confirmado_con_checksum CHECK (((archivo_estado <> 'confirmado'::text) OR ((checksum_archivo IS NOT NULL) AND (archivo_bytes IS NOT NULL)))),
    CONSTRAINT ck_vigencia_documento CHECK ((vigente_desde <= vigente_hasta)),
    CONSTRAINT documento_archivo_bytes_check CHECK (((archivo_bytes IS NULL) OR (archivo_bytes >= 0))),
    CONSTRAINT documento_archivo_estado_check CHECK ((archivo_estado = ANY (ARRAY['sin_archivo'::text, 'subida_pendiente'::text, 'confirmado'::text, 'purga_pendiente'::text, 'purgado'::text]))),
    CONSTRAINT documento_confianza_extraccion_check CHECK ((confianza_extraccion = ANY (ARRAY['alta'::text, 'media'::text, 'baja'::text]))),
    CONSTRAINT documento_estado_confirmacion_check CHECK ((estado_confirmacion = ANY (ARRAY['declarado'::text, 'verificado'::text, 'confirmado_en_fuente'::text]))),
    CONSTRAINT documento_estado_version_check CHECK ((estado_version = ANY (ARRAY['vigente'::text, 'sucedida'::text, 'revertida_por_lote'::text, 'rechazada'::text]))),
    CONSTRAINT documento_origen_check CHECK ((origen = ANY (ARRAY['planilla'::text, 'carga_manual'::text, 'drive'::text])))
);
ALTER TABLE ONLY modulo1.documento FORCE ROW LEVEL SECURITY;
-- Name: evaluacion_habilitacion; Type: TABLE; Schema: modulo1; Owner: -
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
    modo text DEFAULT 'decision'::text NOT NULL,
    secuencia bigint NOT NULL,
    origen_sujetos text DEFAULT 'explicito'::text NOT NULL,
    CONSTRAINT ck_eval_origen_sujetos CHECK ((origen_sujetos = ANY (ARRAY['explicito'::text, 'custodia_por_defecto'::text]))),
    CONSTRAINT ck_excepcion_nunca_verde CHECK (((resultado_de_decision <> 'puede_asignarse_bajo_excepcion'::text) OR (veredicto_de_cumplimiento = ANY (ARRAY['no_habilitado'::text, 'vence_durante_el_trabajo'::text])))),
    CONSTRAINT evaluacion_habilitacion_modo_check CHECK ((modo = 'decision'::text)),
    CONSTRAINT evaluacion_habilitacion_resultado_de_decision_check CHECK ((resultado_de_decision = ANY (ARRAY['puede_asignarse'::text, 'puede_asignarse_bajo_excepcion'::text, 'no_puede_asignarse'::text]))),
    CONSTRAINT evaluacion_habilitacion_veredicto_de_cumplimiento_check CHECK ((veredicto_de_cumplimiento = ANY (ARRAY['habilitado'::text, 'vence_durante_el_trabajo'::text, 'no_habilitado'::text, 'requiere_revision'::text])))
);
ALTER TABLE ONLY modulo1.evaluacion_habilitacion FORCE ROW LEVEL SECURITY;
-- Name: evaluacion_habilitacion_secuencia_seq; Type: SEQUENCE; Schema: modulo1; Owner: -
CREATE SEQUENCE modulo1.evaluacion_habilitacion_secuencia_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
-- Name: evaluacion_habilitacion_secuencia_seq; Type: SEQUENCE OWNED BY; Schema: modulo1; Owner: -
ALTER SEQUENCE modulo1.evaluacion_habilitacion_secuencia_seq OWNED BY modulo1.evaluacion_habilitacion.secuencia;
-- Name: evaluacion_sujeto_propuesto; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.evaluacion_sujeto_propuesto (
    tenant_id uuid NOT NULL,
    evaluacion_id uuid NOT NULL,
    sujeto_id text NOT NULL,
    tipo_sujeto_al_proponer text NOT NULL,
    CONSTRAINT ck_esp_tipo_snapshot CHECK ((tipo_sujeto_al_proponer = ANY (ARRAY['persona'::text, 'vehiculo'::text, 'equipo'::text])))
);
ALTER TABLE ONLY modulo1.evaluacion_sujeto_propuesto FORCE ROW LEVEL SECURITY;
-- Name: event_log; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.event_log (
    id bigint NOT NULL,
    tenant_id uuid NOT NULL,
    evento_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tipo text NOT NULL,
    payload jsonb NOT NULL,
    ocurrido_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.event_log FORCE ROW LEVEL SECURITY;
-- Name: event_log_id_seq; Type: SEQUENCE; Schema: modulo1; Owner: -
CREATE SEQUENCE modulo1.event_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
-- Name: event_log_id_seq; Type: SEQUENCE OWNED BY; Schema: modulo1; Owner: -
ALTER SEQUENCE modulo1.event_log_id_seq OWNED BY modulo1.event_log.id;
-- Name: excepcion; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: idempotency_keys; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.idempotency_keys (
    tenant_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    resultado jsonb,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    expira_en timestamp with time zone NOT NULL,
    estado text NOT NULL,
    fingerprint text,
    reservada_en timestamp with time zone DEFAULT now() NOT NULL,
    reservada_hasta timestamp with time zone DEFAULT (now() + '00:02:00'::interval) NOT NULL,
    actor_id text NOT NULL,
    reservation_token uuid,
    CONSTRAINT ck_idem_estado CHECK ((estado = ANY (ARRAY['en_proceso'::text, 'completada'::text]))),
    CONSTRAINT ck_idem_fingerprint_obligatorio CHECK ((fingerprint IS NOT NULL)),
    CONSTRAINT ck_idem_resultado_segun_estado CHECK ((((estado = 'completada'::text) AND (resultado IS NOT NULL)) OR ((estado = 'en_proceso'::text) AND (resultado IS NULL)))),
    CONSTRAINT ck_idem_token_segun_estado CHECK ((((estado = 'en_proceso'::text) AND (reservation_token IS NOT NULL)) OR (estado = 'completada'::text)))
);
ALTER TABLE ONLY modulo1.idempotency_keys FORCE ROW LEVEL SECURITY;
-- Name: induccion; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: job_queue; Type: TABLE; Schema: modulo1; Owner: -
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
    lease_token uuid,
    ultimo_error text,
    ultimo_error_en timestamp with time zone,
    fallido_en timestamp with time zone,
    CONSTRAINT ck_job_lease_token_segun_estado CHECK ((((estado = 'en_curso'::text) AND (lease_token IS NOT NULL) AND (lease_hasta IS NOT NULL)) OR ((estado <> 'en_curso'::text) AND (lease_token IS NULL)))),
    CONSTRAINT job_queue_cola_check CHECK ((cola = ANY (ARRAY['drenaje_outbox'::text, 'notificaciones'::text, 'evidencia_qr'::text, 'score_documental'::text, 'validacion_evidencia'::text]))),
    CONSTRAINT job_queue_estado_check CHECK ((estado = ANY (ARRAY['pendiente'::text, 'en_curso'::text, 'completado'::text, 'fallido'::text])))
);
ALTER TABLE ONLY modulo1.job_queue FORCE ROW LEVEL SECURITY;
-- Name: job_queue_id_seq; Type: SEQUENCE; Schema: modulo1; Owner: -
CREATE SEQUENCE modulo1.job_queue_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
-- Name: job_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: modulo1; Owner: -
ALTER SEQUENCE modulo1.job_queue_id_seq OWNED BY modulo1.job_queue.id;
-- Name: latido_proceso; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.latido_proceso (
    latido_id uuid DEFAULT gen_random_uuid() NOT NULL,
    nombre text NOT NULL,
    tenant_id uuid,
    ultimo_ok timestamp with time zone,
    ultimo_error timestamp with time zone,
    detalle jsonb DEFAULT '{}'::jsonb NOT NULL,
    actualizado_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.latido_proceso FORCE ROW LEVEL SECURITY;
-- Name: legajo; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: linea_requisito; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.linea_requisito (
    matriz_version_id uuid NOT NULL,
    requisito_definicion_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    clasificacion text NOT NULL,
    bloqueante_durante_ejecucion boolean NOT NULL,
    CONSTRAINT linea_requisito_clasificacion_check CHECK ((clasificacion = ANY (ARRAY['bloqueante_duro'::text, 'excepcionable'::text])))
);
ALTER TABLE ONLY modulo1.linea_requisito FORCE ROW LEVEL SECURITY;
-- Name: lote_importacion; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: matriz_requisitos; Type: TABLE; Schema: modulo1; Owner: -
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
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    matriz_global_id uuid,
    copiada_de_version integer,
    CONSTRAINT ck_matriz_copia_coherente CHECK ((((matriz_global_id IS NULL) AND (copiada_de_version IS NULL)) OR ((matriz_global_id IS NOT NULL) AND (copiada_de_version IS NOT NULL))))
);
ALTER TABLE ONLY modulo1.matriz_requisitos FORCE ROW LEVEL SECURITY;
-- Name: oc; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: outbox_events; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.outbox_events (
    evento_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    tipo text NOT NULL,
    payload jsonb NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    procesado_en timestamp with time zone,
    intentos integer DEFAULT 0 NOT NULL,
    clave_dedup text,
    version_contrato text DEFAULT '1.0'::text NOT NULL,
    CONSTRAINT outbox_events_tipo_check CHECK ((tipo = ANY (ARRAY['HabilitacionRequiereRevaluacion'::text, 'CumplimientoEmpresaAfectado'::text])))
);
ALTER TABLE ONLY modulo1.outbox_events FORCE ROW LEVEL SECURITY;
-- Name: periodo_custodia; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: plantilla_aviso; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.plantilla_aviso (
    tenant_id uuid NOT NULL,
    plantilla_tipo text NOT NULL,
    plantilla_global_id uuid NOT NULL,
    version_nueva integer NOT NULL,
    notificado_en timestamp with time zone DEFAULT now() NOT NULL,
    evento_id uuid,
    CONSTRAINT plantilla_aviso_plantilla_tipo_check CHECK ((plantilla_tipo = ANY (ARRAY['matriz'::text, 'definicion_requisito'::text])))
);
ALTER TABLE ONLY modulo1.plantilla_aviso FORCE ROW LEVEL SECURITY;
-- Name: politica_evento_procesado; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.politica_evento_procesado (
    tenant_id uuid NOT NULL,
    evento_id uuid NOT NULL,
    tipo text NOT NULL,
    procesado_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.politica_evento_procesado FORCE ROW LEVEL SECURITY;
-- Name: refresh_token; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.refresh_token (
    token_hash text NOT NULL,
    tenant_id uuid NOT NULL,
    usuario_id uuid NOT NULL,
    expira_en timestamp with time zone NOT NULL,
    revocado_en timestamp with time zone,
    creado_en timestamp with time zone DEFAULT now() NOT NULL
);
ALTER TABLE ONLY modulo1.refresh_token FORCE ROW LEVEL SECURITY;
-- Name: requisito_particular; Type: TABLE; Schema: modulo1; Owner: -
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
-- Name: tenant; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.tenant (
    tenant_id uuid DEFAULT gen_random_uuid() NOT NULL,
    nombre text NOT NULL,
    zona_horaria text DEFAULT 'America/Argentina/Buenos_Aires'::text NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    slug text NOT NULL
);
ALTER TABLE ONLY modulo1.tenant FORCE ROW LEVEL SECURITY;
-- Name: tenant_slug; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.tenant_slug (
    slug text NOT NULL,
    tenant_id uuid NOT NULL
);
-- Name: usuario; Type: TABLE; Schema: modulo1; Owner: -
CREATE TABLE modulo1.usuario (
    usuario_id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    email text NOT NULL,
    nombre text NOT NULL,
    password_hash text NOT NULL,
    roles text[] NOT NULL,
    sujeto_id text,
    activo boolean DEFAULT true NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_usuario_roles_no_vacio CHECK ((array_length(roles, 1) > 0)),
    CONSTRAINT ck_usuario_roles_validos CHECK ((roles <@ ARRAY['configuracion'::text, 'responsable_legajos'::text, 'supervisor'::text, 'tecnico'::text]))
);
ALTER TABLE ONLY modulo1.usuario FORCE ROW LEVEL SECURITY;
-- Name: definicion_requisito_global; Type: TABLE; Schema: plataforma; Owner: -
CREATE TABLE plataforma.definicion_requisito_global (
    definicion_global_id uuid DEFAULT gen_random_uuid() NOT NULL,
    nombre text NOT NULL,
    categoria text NOT NULL,
    tipo_sujeto_aplicable text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    activa boolean DEFAULT true NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    descripcion text,
    actualizado_en timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT definicion_requisito_global_categoria_check CHECK ((categoria = ANY (ARRAY['documento'::text, 'competencia'::text, 'induccion'::text]))),
    CONSTRAINT definicion_requisito_global_tipo_sujeto_aplicable_check CHECK ((tipo_sujeto_aplicable = ANY (ARRAY['empresa'::text, 'persona'::text, 'vehiculo'::text, 'equipo'::text])))
);
-- Name: linea_matriz_global; Type: TABLE; Schema: plataforma; Owner: -
CREATE TABLE plataforma.linea_matriz_global (
    matriz_global_id uuid NOT NULL,
    definicion_global_id uuid NOT NULL,
    clasificacion text NOT NULL,
    bloqueante_durante_ejecucion boolean DEFAULT false NOT NULL,
    CONSTRAINT linea_matriz_global_clasificacion_check CHECK ((clasificacion = ANY (ARRAY['bloqueante_duro'::text, 'excepcionable'::text])))
);
-- Name: matriz_global; Type: TABLE; Schema: plataforma; Owner: -
CREATE TABLE plataforma.matriz_global (
    matriz_global_id uuid DEFAULT gen_random_uuid() NOT NULL,
    operadora text NOT NULL,
    tipo_servicio text NOT NULL,
    descripcion text,
    version integer DEFAULT 1 NOT NULL,
    activa boolean DEFAULT true NOT NULL,
    fuente text,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    actualizado_en timestamp with time zone DEFAULT now() NOT NULL
);
-- Name: evaluacion_habilitacion secuencia; Type: DEFAULT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_habilitacion ALTER COLUMN secuencia SET DEFAULT nextval('modulo1.evaluacion_habilitacion_secuencia_seq'::regclass);
-- Name: event_log id; Type: DEFAULT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.event_log ALTER COLUMN id SET DEFAULT nextval('modulo1.event_log_id_seq'::regclass);
-- Name: job_queue id; Type: DEFAULT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.job_queue ALTER COLUMN id SET DEFAULT nextval('modulo1.job_queue_id_seq'::regclass);
-- Name: acreditacion_competencia acreditacion_competencia_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.acreditacion_competencia
    ADD CONSTRAINT acreditacion_competencia_pkey PRIMARY KEY (acreditacion_id);
-- Name: asignacion_supervisor asignacion_supervisor_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.asignacion_supervisor
    ADD CONSTRAINT asignacion_supervisor_pkey PRIMARY KEY (asignacion_id);
-- Name: aviso_incumplimiento_empresa_causa aviso_incumplimiento_empresa_causa_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_incumplimiento_empresa_causa
    ADD CONSTRAINT aviso_incumplimiento_empresa_causa_pkey PRIMARY KEY (causa_id);
-- Name: aviso_incumplimiento_empresa aviso_incumplimiento_empresa_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_incumplimiento_empresa
    ADD CONSTRAINT aviso_incumplimiento_empresa_pkey PRIMARY KEY (aviso_id);
-- Name: aviso_revaluacion_causa aviso_revaluacion_causa_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion_causa
    ADD CONSTRAINT aviso_revaluacion_causa_pkey PRIMARY KEY (tenant_id, aviso_id, evento_id);
-- Name: aviso_revaluacion aviso_revaluacion_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion
    ADD CONSTRAINT aviso_revaluacion_pkey PRIMARY KEY (aviso_id);
-- Name: constancia_cliente constancia_cliente_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT constancia_cliente_pkey PRIMARY KEY (constancia_id);
-- Name: custodia_recurso custodia_recurso_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT custodia_recurso_pkey PRIMARY KEY (custodia_id);
-- Name: definicion_requisito definicion_requisito_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT definicion_requisito_pkey PRIMARY KEY (requisito_definicion_id);
-- Name: documento documento_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT documento_pkey PRIMARY KEY (documento_id);
-- Name: evaluacion_habilitacion evaluacion_habilitacion_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_habilitacion
    ADD CONSTRAINT evaluacion_habilitacion_pkey PRIMARY KEY (referencia_evaluacion);
-- Name: evaluacion_sujeto_propuesto evaluacion_sujeto_propuesto_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_sujeto_propuesto
    ADD CONSTRAINT evaluacion_sujeto_propuesto_pkey PRIMARY KEY (tenant_id, evaluacion_id, sujeto_id);
-- Name: event_log event_log_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.event_log
    ADD CONSTRAINT event_log_pkey PRIMARY KEY (id);
-- Name: excepcion excepcion_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT excepcion_pkey PRIMARY KEY (excepcion_id);
-- Name: idempotency_keys idempotency_keys_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.idempotency_keys
    ADD CONSTRAINT idempotency_keys_pkey PRIMARY KEY (tenant_id, actor_id, idempotency_key);
-- Name: induccion induccion_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT induccion_pkey PRIMARY KEY (induccion_id);
-- Name: job_queue job_queue_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.job_queue
    ADD CONSTRAINT job_queue_pkey PRIMARY KEY (id);
-- Name: latido_proceso latido_proceso_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.latido_proceso
    ADD CONSTRAINT latido_proceso_pkey PRIMARY KEY (latido_id);
-- Name: legajo legajo_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.legajo
    ADD CONSTRAINT legajo_pkey PRIMARY KEY (legajo_id);
-- Name: linea_requisito linea_requisito_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT linea_requisito_pkey PRIMARY KEY (matriz_version_id, requisito_definicion_id);
-- Name: lote_importacion lote_importacion_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.lote_importacion
    ADD CONSTRAINT lote_importacion_pkey PRIMARY KEY (lote_id);
-- Name: matriz_requisitos matriz_requisitos_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT matriz_requisitos_pkey PRIMARY KEY (matriz_version_id);
-- Name: oc oc_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT oc_pkey PRIMARY KEY (oc_id);
-- Name: outbox_events outbox_events_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.outbox_events
    ADD CONSTRAINT outbox_events_pkey PRIMARY KEY (evento_id);
-- Name: periodo_custodia periodo_custodia_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT periodo_custodia_pkey PRIMARY KEY (periodo_id);
-- Name: plantilla_aviso plantilla_aviso_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.plantilla_aviso
    ADD CONSTRAINT plantilla_aviso_pkey PRIMARY KEY (tenant_id, plantilla_tipo, plantilla_global_id, version_nueva);
-- Name: politica_evento_procesado politica_evento_procesado_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.politica_evento_procesado
    ADD CONSTRAINT politica_evento_procesado_pkey PRIMARY KEY (tenant_id, evento_id);
-- Name: refresh_token refresh_token_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.refresh_token
    ADD CONSTRAINT refresh_token_pkey PRIMARY KEY (token_hash);
-- Name: requisito_particular requisito_particular_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT requisito_particular_pkey PRIMARY KEY (requisito_particular_id);
-- Name: tenant tenant_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.tenant
    ADD CONSTRAINT tenant_pkey PRIMARY KEY (tenant_id);
-- Name: tenant_slug tenant_slug_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.tenant_slug
    ADD CONSTRAINT tenant_slug_pkey PRIMARY KEY (slug);
-- Name: tenant_slug tenant_slug_tenant_id_key; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.tenant_slug
    ADD CONSTRAINT tenant_slug_tenant_id_key UNIQUE (tenant_id);
-- Name: aviso_incumplimiento_empresa uq_aie_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_incumplimiento_empresa
    ADD CONSTRAINT uq_aie_tenant_id UNIQUE (tenant_id, aviso_id);
-- Name: aviso_revaluacion uq_aviso_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion
    ADD CONSTRAINT uq_aviso_tenant_id UNIQUE (tenant_id, aviso_id);
-- Name: constancia_cliente uq_constancia_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT uq_constancia_tenant_id UNIQUE (tenant_id, constancia_id);
-- Name: custodia_recurso uq_custodia_recurso; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT uq_custodia_recurso UNIQUE (tenant_id, recurso_id, tipo_recurso);
-- Name: custodia_recurso uq_custodia_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT uq_custodia_tenant_id UNIQUE (tenant_id, custodia_id);
-- Name: definicion_requisito uq_definicion_clave_negocio; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT uq_definicion_clave_negocio UNIQUE NULLS NOT DISTINCT (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id);
-- Name: definicion_requisito uq_definicion_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT uq_definicion_tenant_id UNIQUE (tenant_id, requisito_definicion_id);
-- Name: documento uq_documento_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT uq_documento_tenant_id UNIQUE (tenant_id, documento_id);
-- Name: evaluacion_habilitacion uq_evaluacion_tenant_ref; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_habilitacion
    ADD CONSTRAINT uq_evaluacion_tenant_ref UNIQUE (tenant_id, referencia_evaluacion);
-- Name: event_log uq_event_log_tenant_evento; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.event_log
    ADD CONSTRAINT uq_event_log_tenant_evento UNIQUE (tenant_id, evento_id);
-- Name: legajo uq_legajo_sujeto; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.legajo
    ADD CONSTRAINT uq_legajo_sujeto UNIQUE (tenant_id, sujeto_id, tipo_sujeto);
-- Name: legajo uq_legajo_tenant_sujeto; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.legajo
    ADD CONSTRAINT uq_legajo_tenant_sujeto UNIQUE (tenant_id, sujeto_id);
-- Name: lote_importacion uq_lote_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.lote_importacion
    ADD CONSTRAINT uq_lote_tenant_id UNIQUE (tenant_id, lote_id);
-- Name: matriz_requisitos uq_matriz_clave_version; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT uq_matriz_clave_version UNIQUE (tenant_id, cliente_id, locacion_id, tipo_servicio_id, version);
-- Name: matriz_requisitos uq_matriz_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT uq_matriz_tenant_id UNIQUE (tenant_id, matriz_version_id);
-- Name: oc uq_oc_clave_origen; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT uq_oc_clave_origen UNIQUE (tenant_id, clave_origen);
-- Name: outbox_events uq_outbox_dedup; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.outbox_events
    ADD CONSTRAINT uq_outbox_dedup UNIQUE (tenant_id, clave_dedup);
-- Name: periodo_custodia uq_periodo_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT uq_periodo_tenant_id UNIQUE (tenant_id, periodo_id);
-- Name: requisito_particular uq_requisito_particular; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT uq_requisito_particular UNIQUE (tenant_id, commitment_id, requisito_definicion_id);
-- Name: usuario uq_usuario_tenant_email; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.usuario
    ADD CONSTRAINT uq_usuario_tenant_email UNIQUE (tenant_id, email);
-- Name: usuario uq_usuario_tenant_id; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.usuario
    ADD CONSTRAINT uq_usuario_tenant_id UNIQUE (tenant_id, usuario_id);
-- Name: usuario usuario_pkey; Type: CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.usuario
    ADD CONSTRAINT usuario_pkey PRIMARY KEY (usuario_id);
-- Name: definicion_requisito_global definicion_requisito_global_pkey; Type: CONSTRAINT; Schema: plataforma; Owner: -
ALTER TABLE ONLY plataforma.definicion_requisito_global
    ADD CONSTRAINT definicion_requisito_global_pkey PRIMARY KEY (definicion_global_id);
-- Name: linea_matriz_global linea_matriz_global_pkey; Type: CONSTRAINT; Schema: plataforma; Owner: -
ALTER TABLE ONLY plataforma.linea_matriz_global
    ADD CONSTRAINT linea_matriz_global_pkey PRIMARY KEY (matriz_global_id, definicion_global_id);
-- Name: matriz_global matriz_global_pkey; Type: CONSTRAINT; Schema: plataforma; Owner: -
ALTER TABLE ONLY plataforma.matriz_global
    ADD CONSTRAINT matriz_global_pkey PRIMARY KEY (matriz_global_id);
-- Name: definicion_requisito_global uq_definicion_global_clave; Type: CONSTRAINT; Schema: plataforma; Owner: -
ALTER TABLE ONLY plataforma.definicion_requisito_global
    ADD CONSTRAINT uq_definicion_global_clave UNIQUE (nombre, categoria, tipo_sujeto_aplicable);
-- Name: matriz_global uq_matriz_global_clave; Type: CONSTRAINT; Schema: plataforma; Owner: -
ALTER TABLE ONLY plataforma.matriz_global
    ADD CONSTRAINT uq_matriz_global_clave UNIQUE (operadora, tipo_servicio);
-- Name: ix_acreditacion_competencia__persona_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_acreditacion_competencia__persona_id ON modulo1.acreditacion_competencia USING btree (tenant_id, persona_id);
-- Name: ix_acreditacion_tenant_persona; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_acreditacion_tenant_persona ON modulo1.acreditacion_competencia USING btree (tenant_id, persona_id, requisito_definicion_id);
-- Name: ix_asignacion_supervisor__sujeto_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_asignacion_supervisor__sujeto_id ON modulo1.asignacion_supervisor USING btree (tenant_id, sujeto_id);
-- Name: ix_asignacion_supervisor_sup; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_asignacion_supervisor_sup ON modulo1.asignacion_supervisor USING btree (tenant_id, supervisor_usuario_id);
-- Name: ix_aviso_revaluacion_commitment; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_aviso_revaluacion_commitment ON modulo1.aviso_revaluacion USING btree (tenant_id, commitment_id, estado);
-- Name: ix_constancia_cliente__commitment_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_constancia_cliente__commitment_id ON modulo1.constancia_cliente USING btree (tenant_id, commitment_id);
-- Name: ix_constancia_cliente__sujeto_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_constancia_cliente__sujeto_id ON modulo1.constancia_cliente USING btree (tenant_id, sujeto_id);
-- Name: ix_constancia_tenant_sujeto; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_constancia_tenant_sujeto ON modulo1.constancia_cliente USING btree (tenant_id, sujeto_id, requisito_definicion_id, cliente_id);
-- Name: ix_definicion_requisito_tenant; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_definicion_requisito_tenant ON modulo1.definicion_requisito USING btree (tenant_id, activa);
-- Name: ix_documento__sujeto_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_documento__sujeto_id ON modulo1.documento USING btree (tenant_id, sujeto_id);
-- Name: ix_documento_archivo_estado; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_documento_archivo_estado ON modulo1.documento USING btree (tenant_id, archivo_estado) WHERE (archivo_estado = ANY (ARRAY['subida_pendiente'::text, 'purga_pendiente'::text]));
-- Name: ix_documento_sucede_a; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_documento_sucede_a ON modulo1.documento USING btree (tenant_id, sucede_a);
-- Name: ix_documento_tenant_sujeto; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_documento_tenant_sujeto ON modulo1.documento USING btree (tenant_id, sujeto_id, requisito_definicion_id);
-- Name: ix_esp_sujeto; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_esp_sujeto ON modulo1.evaluacion_sujeto_propuesto USING btree (tenant_id, sujeto_id);
-- Name: ix_eval_commitment_orden; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_eval_commitment_orden ON modulo1.evaluacion_habilitacion USING btree (tenant_id, commitment_id, creado_en DESC, secuencia DESC);
-- Name: ix_eval_version_matriz; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_eval_version_matriz ON modulo1.evaluacion_habilitacion USING btree (tenant_id, ((version_matriz ->> 'matriz_version_id'::text)));
-- Name: ix_evaluacion_tenant_commitment; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_evaluacion_tenant_commitment ON modulo1.evaluacion_habilitacion USING btree (tenant_id, commitment_id, creado_en DESC);
-- Name: ix_event_log_tenant; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_event_log_tenant ON modulo1.event_log USING btree (tenant_id, ocurrido_en DESC);
-- Name: ix_excepcion__commitment_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_excepcion__commitment_id ON modulo1.excepcion USING btree (tenant_id, commitment_id);
-- Name: ix_excepcion__referencia_evaluacion; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_excepcion__referencia_evaluacion ON modulo1.excepcion USING btree (tenant_id, referencia_evaluacion);
-- Name: ix_excepcion__sujeto_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_excepcion__sujeto_id ON modulo1.excepcion USING btree (tenant_id, sujeto_id);
-- Name: ix_excepcion_tenant_sujeto; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_excepcion_tenant_sujeto ON modulo1.excepcion USING btree (tenant_id, sujeto_id, requisito_definicion_id, commitment_id);
-- Name: ix_induccion__persona_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_induccion__persona_id ON modulo1.induccion USING btree (tenant_id, persona_id);
-- Name: ix_induccion_tenant_persona; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_induccion_tenant_persona ON modulo1.induccion USING btree (tenant_id, persona_id, requisito_definicion_id);
-- Name: ix_job_queue_disponibles; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_job_queue_disponibles ON modulo1.job_queue USING btree (cola, disponible_en) WHERE (estado = 'pendiente'::text);
-- Name: ix_job_queue_fallidos; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_job_queue_fallidos ON modulo1.job_queue USING btree (cola, fallido_en) WHERE (estado = 'fallido'::text);
-- Name: ix_job_queue_lease_vencido; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_job_queue_lease_vencido ON modulo1.job_queue USING btree (lease_hasta) WHERE (estado = 'en_curso'::text);
-- Name: ix_legajo_tenant; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_legajo_tenant ON modulo1.legajo USING btree (tenant_id, tipo_sujeto);
-- Name: ix_lote_importacion_tenant; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_lote_importacion_tenant ON modulo1.lote_importacion USING btree (tenant_id, entidad);
-- Name: ix_matriz_tenant_clave; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_matriz_tenant_clave ON modulo1.matriz_requisitos USING btree (tenant_id, cliente_id, locacion_id, tipo_servicio_id, vigente_desde);
-- Name: ix_oc_clave_matriz; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_oc_clave_matriz ON modulo1.oc USING btree (tenant_id, cliente_id, locacion_id, tipo_servicio_id);
-- Name: ix_oc_tenant_estado; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_oc_tenant_estado ON modulo1.oc USING btree (tenant_id, estado, locacion_id);
-- Name: ix_outbox_pendientes; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_outbox_pendientes ON modulo1.outbox_events USING btree (creado_en) WHERE (procesado_en IS NULL);
-- Name: ix_periodo_custodia__custodio_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_periodo_custodia__custodio_id ON modulo1.periodo_custodia USING btree (tenant_id, custodio_id);
-- Name: ix_refresh_token_usuario; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_refresh_token_usuario ON modulo1.refresh_token USING btree (tenant_id, usuario_id);
-- Name: ix_requisito_particular__commitment_id; Type: INDEX; Schema: modulo1; Owner: -
CREATE INDEX ix_requisito_particular__commitment_id ON modulo1.requisito_particular USING btree (tenant_id, commitment_id);
-- Name: uq_aie_abierto_por_tenant; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_aie_abierto_por_tenant ON modulo1.aviso_incumplimiento_empresa USING btree (tenant_id) WHERE (estado = 'abierto'::text);
-- Name: uq_aiec_activa; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_aiec_activa ON modulo1.aviso_incumplimiento_empresa_causa USING btree (tenant_id, aviso_id, requisito_definicion_id) WHERE (estado = 'activa'::text);
-- Name: uq_asignacion_supervisor_vigente; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_asignacion_supervisor_vigente ON modulo1.asignacion_supervisor USING btree (tenant_id, sujeto_id) WHERE (estado = 'vigente'::text);
-- Name: uq_aviso_revaluacion_abierto; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_aviso_revaluacion_abierto ON modulo1.aviso_revaluacion USING btree (tenant_id, referencia_evaluacion) WHERE (estado = 'abierto'::text);
-- Name: uq_constancia_especifica_activa; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_constancia_especifica_activa ON modulo1.constancia_cliente USING btree (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id) WHERE ((estado = 'vigente'::text) AND (commitment_id IS NOT NULL));
-- Name: uq_constancia_general_activa; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_constancia_general_activa ON modulo1.constancia_cliente USING btree (tenant_id, sujeto_id, requisito_definicion_id, cliente_id) WHERE ((estado = 'vigente'::text) AND (commitment_id IS NULL));
-- Name: uq_documento_vigente; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_documento_vigente ON modulo1.documento USING btree (tenant_id, sujeto_id, requisito_definicion_id) WHERE ((estado_version = 'vigente'::text) AND (requisito_definicion_id IS NOT NULL));
-- Name: uq_excepcion_activa; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_excepcion_activa ON modulo1.excepcion USING btree (tenant_id, sujeto_id, requisito_definicion_id, commitment_id) WHERE (estado = 'otorgada'::text);
-- Name: uq_latido_proceso; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_latido_proceso ON modulo1.latido_proceso USING btree (nombre, COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid));
-- Name: uq_periodo_custodia_vigente; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_periodo_custodia_vigente ON modulo1.periodo_custodia USING btree (custodia_id) WHERE (estado = 'vigente'::text);
-- Name: uq_tenant_slug; Type: INDEX; Schema: modulo1; Owner: -
CREATE UNIQUE INDEX uq_tenant_slug ON modulo1.tenant USING btree (slug);
-- Name: tenant trg_tenant_slug; Type: TRIGGER; Schema: modulo1; Owner: -
CREATE TRIGGER trg_tenant_slug AFTER INSERT OR DELETE OR UPDATE OF slug, tenant_id ON modulo1.tenant FOR EACH ROW EXECUTE FUNCTION modulo1.sincronizar_tenant_slug();
-- Name: acreditacion_competencia acreditacion_competencia_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.acreditacion_competencia
    ADD CONSTRAINT acreditacion_competencia_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: constancia_cliente constancia_cliente_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT constancia_cliente_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: custodia_recurso custodia_recurso_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT custodia_recurso_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: definicion_requisito definicion_requisito_definicion_global_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT definicion_requisito_definicion_global_id_fkey FOREIGN KEY (definicion_global_id) REFERENCES plataforma.definicion_requisito_global(definicion_global_id);
-- Name: definicion_requisito definicion_requisito_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.definicion_requisito
    ADD CONSTRAINT definicion_requisito_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: documento documento_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT documento_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: evaluacion_habilitacion evaluacion_habilitacion_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_habilitacion
    ADD CONSTRAINT evaluacion_habilitacion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: event_log event_log_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.event_log
    ADD CONSTRAINT event_log_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: excepcion excepcion_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT excepcion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: acreditacion_competencia fk_acreditacion_competencia__persona_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.acreditacion_competencia
    ADD CONSTRAINT fk_acreditacion_competencia__persona_id FOREIGN KEY (tenant_id, persona_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: acreditacion_competencia fk_acreditacion_competencia__requisito_definicion_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.acreditacion_competencia
    ADD CONSTRAINT fk_acreditacion_competencia__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: aviso_incumplimiento_empresa_causa fk_aiec_aviso; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_incumplimiento_empresa_causa
    ADD CONSTRAINT fk_aiec_aviso FOREIGN KEY (tenant_id, aviso_id) REFERENCES modulo1.aviso_incumplimiento_empresa(tenant_id, aviso_id) ON DELETE CASCADE;
-- Name: aviso_incumplimiento_empresa_causa fk_aiec_requisito; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_incumplimiento_empresa_causa
    ADD CONSTRAINT fk_aiec_requisito FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: aviso_revaluacion_causa fk_arc_aviso; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion_causa
    ADD CONSTRAINT fk_arc_aviso FOREIGN KEY (tenant_id, aviso_id) REFERENCES modulo1.aviso_revaluacion(tenant_id, aviso_id) ON DELETE CASCADE;
-- Name: asignacion_supervisor fk_asignacion_supervisor__sujeto_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.asignacion_supervisor
    ADD CONSTRAINT fk_asignacion_supervisor__sujeto_id FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: asignacion_supervisor fk_asignacion_supervisor__supervisor_usuario_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.asignacion_supervisor
    ADD CONSTRAINT fk_asignacion_supervisor__supervisor_usuario_id FOREIGN KEY (tenant_id, supervisor_usuario_id) REFERENCES modulo1.usuario(tenant_id, usuario_id);
-- Name: aviso_revaluacion fk_aviso_evaluacion; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion
    ADD CONSTRAINT fk_aviso_evaluacion FOREIGN KEY (tenant_id, referencia_evaluacion) REFERENCES modulo1.evaluacion_habilitacion(tenant_id, referencia_evaluacion) ON DELETE CASCADE;
-- Name: aviso_revaluacion fk_aviso_revaluacion__cerrado_por_referencia; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion
    ADD CONSTRAINT fk_aviso_revaluacion__cerrado_por_referencia FOREIGN KEY (tenant_id, cerrado_por_referencia) REFERENCES modulo1.evaluacion_habilitacion(tenant_id, referencia_evaluacion);
-- Name: aviso_revaluacion fk_aviso_revaluacion__commitment_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion
    ADD CONSTRAINT fk_aviso_revaluacion__commitment_id FOREIGN KEY (tenant_id, commitment_id) REFERENCES modulo1.oc(tenant_id, clave_origen);
-- Name: aviso_revaluacion_causa fk_aviso_revaluacion_causa__evento_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.aviso_revaluacion_causa
    ADD CONSTRAINT fk_aviso_revaluacion_causa__evento_id FOREIGN KEY (tenant_id, evento_id) REFERENCES modulo1.event_log(tenant_id, evento_id);
-- Name: constancia_cliente fk_constancia_cliente__commitment_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT fk_constancia_cliente__commitment_id FOREIGN KEY (tenant_id, commitment_id) REFERENCES modulo1.oc(tenant_id, clave_origen);
-- Name: constancia_cliente fk_constancia_cliente__reemplazada_por; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT fk_constancia_cliente__reemplazada_por FOREIGN KEY (tenant_id, reemplazada_por) REFERENCES modulo1.constancia_cliente(tenant_id, constancia_id);
-- Name: constancia_cliente fk_constancia_cliente__requisito_definicion_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT fk_constancia_cliente__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: constancia_cliente fk_constancia_cliente__sujeto_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.constancia_cliente
    ADD CONSTRAINT fk_constancia_cliente__sujeto_id FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: custodia_recurso fk_custodia_recurso__recurso_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.custodia_recurso
    ADD CONSTRAINT fk_custodia_recurso__recurso_id FOREIGN KEY (tenant_id, recurso_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: documento fk_documento__lote_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT fk_documento__lote_id FOREIGN KEY (tenant_id, lote_id) REFERENCES modulo1.lote_importacion(tenant_id, lote_id);
-- Name: documento fk_documento__requisito_definicion_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT fk_documento__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: documento fk_documento__sucede_a; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT fk_documento__sucede_a FOREIGN KEY (tenant_id, sucede_a) REFERENCES modulo1.documento(tenant_id, documento_id);
-- Name: documento fk_documento__sujeto_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.documento
    ADD CONSTRAINT fk_documento__sujeto_id FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: evaluacion_sujeto_propuesto fk_esp_evaluacion; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_sujeto_propuesto
    ADD CONSTRAINT fk_esp_evaluacion FOREIGN KEY (tenant_id, evaluacion_id) REFERENCES modulo1.evaluacion_habilitacion(tenant_id, referencia_evaluacion) ON DELETE CASCADE;
-- Name: evaluacion_sujeto_propuesto fk_esp_legajo; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_sujeto_propuesto
    ADD CONSTRAINT fk_esp_legajo FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: evaluacion_habilitacion fk_evaluacion_habilitacion__commitment_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.evaluacion_habilitacion
    ADD CONSTRAINT fk_evaluacion_habilitacion__commitment_id FOREIGN KEY (tenant_id, commitment_id) REFERENCES modulo1.oc(tenant_id, clave_origen);
-- Name: excepcion fk_excepcion__commitment_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT fk_excepcion__commitment_id FOREIGN KEY (tenant_id, commitment_id) REFERENCES modulo1.oc(tenant_id, clave_origen);
-- Name: excepcion fk_excepcion__referencia_evaluacion; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT fk_excepcion__referencia_evaluacion FOREIGN KEY (tenant_id, referencia_evaluacion) REFERENCES modulo1.evaluacion_habilitacion(tenant_id, referencia_evaluacion);
-- Name: excepcion fk_excepcion__requisito_definicion_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT fk_excepcion__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: excepcion fk_excepcion__sujeto_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.excepcion
    ADD CONSTRAINT fk_excepcion__sujeto_id FOREIGN KEY (tenant_id, sujeto_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: induccion fk_induccion__evidencia; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT fk_induccion__evidencia FOREIGN KEY (tenant_id, evidencia) REFERENCES modulo1.documento(tenant_id, documento_id);
-- Name: induccion fk_induccion__persona_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT fk_induccion__persona_id FOREIGN KEY (tenant_id, persona_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: induccion fk_induccion__requisito_definicion_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT fk_induccion__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: linea_requisito fk_linea_requisito__matriz_version_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT fk_linea_requisito__matriz_version_id FOREIGN KEY (tenant_id, matriz_version_id) REFERENCES modulo1.matriz_requisitos(tenant_id, matriz_version_id) ON DELETE CASCADE;
-- Name: linea_requisito fk_linea_requisito__requisito_definicion_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT fk_linea_requisito__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: oc fk_oc__lote_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT fk_oc__lote_id FOREIGN KEY (tenant_id, lote_id) REFERENCES modulo1.lote_importacion(tenant_id, lote_id);
-- Name: politica_evento_procesado fk_pep_evento; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.politica_evento_procesado
    ADD CONSTRAINT fk_pep_evento FOREIGN KEY (tenant_id, evento_id) REFERENCES modulo1.event_log(tenant_id, evento_id) ON DELETE CASCADE;
-- Name: periodo_custodia fk_periodo_custodia__corregido_por; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT fk_periodo_custodia__corregido_por FOREIGN KEY (tenant_id, corregido_por) REFERENCES modulo1.periodo_custodia(tenant_id, periodo_id);
-- Name: periodo_custodia fk_periodo_custodia__custodia_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT fk_periodo_custodia__custodia_id FOREIGN KEY (tenant_id, custodia_id) REFERENCES modulo1.custodia_recurso(tenant_id, custodia_id);
-- Name: periodo_custodia fk_periodo_custodia__custodio_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT fk_periodo_custodia__custodio_id FOREIGN KEY (tenant_id, custodio_id) REFERENCES modulo1.legajo(tenant_id, sujeto_id);
-- Name: refresh_token fk_refresh_token__usuario_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.refresh_token
    ADD CONSTRAINT fk_refresh_token__usuario_id FOREIGN KEY (tenant_id, usuario_id) REFERENCES modulo1.usuario(tenant_id, usuario_id);
-- Name: requisito_particular fk_requisito_particular__commitment_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT fk_requisito_particular__commitment_id FOREIGN KEY (tenant_id, commitment_id) REFERENCES modulo1.oc(tenant_id, clave_origen);
-- Name: requisito_particular fk_requisito_particular__requisito_definicion_id; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT fk_requisito_particular__requisito_definicion_id FOREIGN KEY (tenant_id, requisito_definicion_id) REFERENCES modulo1.definicion_requisito(tenant_id, requisito_definicion_id);
-- Name: idempotency_keys idempotency_keys_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.idempotency_keys
    ADD CONSTRAINT idempotency_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: induccion induccion_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.induccion
    ADD CONSTRAINT induccion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: job_queue job_queue_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.job_queue
    ADD CONSTRAINT job_queue_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: latido_proceso latido_proceso_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.latido_proceso
    ADD CONSTRAINT latido_proceso_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id) ON DELETE CASCADE;
-- Name: legajo legajo_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.legajo
    ADD CONSTRAINT legajo_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: linea_requisito linea_requisito_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.linea_requisito
    ADD CONSTRAINT linea_requisito_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: lote_importacion lote_importacion_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.lote_importacion
    ADD CONSTRAINT lote_importacion_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: matriz_requisitos matriz_requisitos_matriz_global_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT matriz_requisitos_matriz_global_id_fkey FOREIGN KEY (matriz_global_id) REFERENCES plataforma.matriz_global(matriz_global_id);
-- Name: matriz_requisitos matriz_requisitos_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.matriz_requisitos
    ADD CONSTRAINT matriz_requisitos_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: oc oc_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.oc
    ADD CONSTRAINT oc_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: outbox_events outbox_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.outbox_events
    ADD CONSTRAINT outbox_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: periodo_custodia periodo_custodia_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.periodo_custodia
    ADD CONSTRAINT periodo_custodia_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: plantilla_aviso plantilla_aviso_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.plantilla_aviso
    ADD CONSTRAINT plantilla_aviso_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: requisito_particular requisito_particular_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.requisito_particular
    ADD CONSTRAINT requisito_particular_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: usuario usuario_tenant_id_fkey; Type: FK CONSTRAINT; Schema: modulo1; Owner: -
ALTER TABLE ONLY modulo1.usuario
    ADD CONSTRAINT usuario_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES modulo1.tenant(tenant_id);
-- Name: linea_matriz_global linea_matriz_global_definicion_global_id_fkey; Type: FK CONSTRAINT; Schema: plataforma; Owner: -
ALTER TABLE ONLY plataforma.linea_matriz_global
    ADD CONSTRAINT linea_matriz_global_definicion_global_id_fkey FOREIGN KEY (definicion_global_id) REFERENCES plataforma.definicion_requisito_global(definicion_global_id);
-- Name: linea_matriz_global linea_matriz_global_matriz_global_id_fkey; Type: FK CONSTRAINT; Schema: plataforma; Owner: -
ALTER TABLE ONLY plataforma.linea_matriz_global
    ADD CONSTRAINT linea_matriz_global_matriz_global_id_fkey FOREIGN KEY (matriz_global_id) REFERENCES plataforma.matriz_global(matriz_global_id) ON DELETE CASCADE;
-- Name: acreditacion_competencia; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.acreditacion_competencia ENABLE ROW LEVEL SECURITY;
-- Name: acreditacion_competencia acreditacion_competencia_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY acreditacion_competencia_aislamiento ON modulo1.acreditacion_competencia USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: asignacion_supervisor; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.asignacion_supervisor ENABLE ROW LEVEL SECURITY;
-- Name: asignacion_supervisor asignacion_supervisor_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY asignacion_supervisor_aislamiento ON modulo1.asignacion_supervisor USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: aviso_incumplimiento_empresa; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.aviso_incumplimiento_empresa ENABLE ROW LEVEL SECURITY;
-- Name: aviso_incumplimiento_empresa aviso_incumplimiento_empresa_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY aviso_incumplimiento_empresa_aislamiento ON modulo1.aviso_incumplimiento_empresa USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: aviso_incumplimiento_empresa_causa; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.aviso_incumplimiento_empresa_causa ENABLE ROW LEVEL SECURITY;
-- Name: aviso_incumplimiento_empresa_causa aviso_incumplimiento_empresa_causa_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY aviso_incumplimiento_empresa_causa_aislamiento ON modulo1.aviso_incumplimiento_empresa_causa USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: aviso_revaluacion; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.aviso_revaluacion ENABLE ROW LEVEL SECURITY;
-- Name: aviso_revaluacion aviso_revaluacion_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY aviso_revaluacion_aislamiento ON modulo1.aviso_revaluacion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: aviso_revaluacion_causa; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.aviso_revaluacion_causa ENABLE ROW LEVEL SECURITY;
-- Name: aviso_revaluacion_causa aviso_revaluacion_causa_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY aviso_revaluacion_causa_aislamiento ON modulo1.aviso_revaluacion_causa USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: constancia_cliente; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.constancia_cliente ENABLE ROW LEVEL SECURITY;
-- Name: constancia_cliente constancia_cliente_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY constancia_cliente_aislamiento ON modulo1.constancia_cliente USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: custodia_recurso; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.custodia_recurso ENABLE ROW LEVEL SECURITY;
-- Name: custodia_recurso custodia_recurso_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY custodia_recurso_aislamiento ON modulo1.custodia_recurso USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: definicion_requisito; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.definicion_requisito ENABLE ROW LEVEL SECURITY;
-- Name: definicion_requisito definicion_requisito_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY definicion_requisito_aislamiento ON modulo1.definicion_requisito USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: documento; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.documento ENABLE ROW LEVEL SECURITY;
-- Name: documento documento_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY documento_aislamiento ON modulo1.documento USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: evaluacion_habilitacion; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.evaluacion_habilitacion ENABLE ROW LEVEL SECURITY;
-- Name: evaluacion_habilitacion evaluacion_habilitacion_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY evaluacion_habilitacion_aislamiento ON modulo1.evaluacion_habilitacion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: evaluacion_sujeto_propuesto; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.evaluacion_sujeto_propuesto ENABLE ROW LEVEL SECURITY;
-- Name: evaluacion_sujeto_propuesto evaluacion_sujeto_propuesto_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY evaluacion_sujeto_propuesto_aislamiento ON modulo1.evaluacion_sujeto_propuesto USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: event_log; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.event_log ENABLE ROW LEVEL SECURITY;
-- Name: event_log event_log_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY event_log_aislamiento ON modulo1.event_log USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: excepcion; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.excepcion ENABLE ROW LEVEL SECURITY;
-- Name: excepcion excepcion_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY excepcion_aislamiento ON modulo1.excepcion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: idempotency_keys; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.idempotency_keys ENABLE ROW LEVEL SECURITY;
-- Name: idempotency_keys idempotency_keys_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY idempotency_keys_aislamiento ON modulo1.idempotency_keys USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: induccion; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.induccion ENABLE ROW LEVEL SECURITY;
-- Name: induccion induccion_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY induccion_aislamiento ON modulo1.induccion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: job_queue; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.job_queue ENABLE ROW LEVEL SECURITY;
-- Name: job_queue job_queue_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY job_queue_aislamiento ON modulo1.job_queue USING (((tenant_id IS NULL) OR (tenant_id = (current_setting('app.current_tenant'::text))::uuid))) WITH CHECK (((tenant_id IS NULL) OR (tenant_id = (current_setting('app.current_tenant'::text))::uuid)));
-- Name: latido_proceso; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.latido_proceso ENABLE ROW LEVEL SECURITY;
-- Name: latido_proceso latido_proceso_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY latido_proceso_aislamiento ON modulo1.latido_proceso USING (((tenant_id IS NULL) OR (tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), ''::text))::uuid))) WITH CHECK (((tenant_id IS NULL) OR (tenant_id = (NULLIF(current_setting('app.current_tenant'::text, true), ''::text))::uuid)));
-- Name: legajo; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.legajo ENABLE ROW LEVEL SECURITY;
-- Name: legajo legajo_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY legajo_aislamiento ON modulo1.legajo USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: linea_requisito; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.linea_requisito ENABLE ROW LEVEL SECURITY;
-- Name: linea_requisito linea_requisito_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY linea_requisito_aislamiento ON modulo1.linea_requisito USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: lote_importacion; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.lote_importacion ENABLE ROW LEVEL SECURITY;
-- Name: lote_importacion lote_importacion_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY lote_importacion_aislamiento ON modulo1.lote_importacion USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: matriz_requisitos; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.matriz_requisitos ENABLE ROW LEVEL SECURITY;
-- Name: matriz_requisitos matriz_requisitos_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY matriz_requisitos_aislamiento ON modulo1.matriz_requisitos USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: oc; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.oc ENABLE ROW LEVEL SECURITY;
-- Name: oc oc_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY oc_aislamiento ON modulo1.oc USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: outbox_events; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.outbox_events ENABLE ROW LEVEL SECURITY;
-- Name: outbox_events outbox_events_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY outbox_events_aislamiento ON modulo1.outbox_events USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: periodo_custodia; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.periodo_custodia ENABLE ROW LEVEL SECURITY;
-- Name: periodo_custodia periodo_custodia_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY periodo_custodia_aislamiento ON modulo1.periodo_custodia USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: plantilla_aviso; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.plantilla_aviso ENABLE ROW LEVEL SECURITY;
-- Name: plantilla_aviso plantilla_aviso_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY plantilla_aviso_aislamiento ON modulo1.plantilla_aviso USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: politica_evento_procesado; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.politica_evento_procesado ENABLE ROW LEVEL SECURITY;
-- Name: politica_evento_procesado politica_evento_procesado_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY politica_evento_procesado_aislamiento ON modulo1.politica_evento_procesado USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: refresh_token; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.refresh_token ENABLE ROW LEVEL SECURITY;
-- Name: refresh_token refresh_token_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY refresh_token_aislamiento ON modulo1.refresh_token USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: requisito_particular; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.requisito_particular ENABLE ROW LEVEL SECURITY;
-- Name: requisito_particular requisito_particular_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY requisito_particular_aislamiento ON modulo1.requisito_particular USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: tenant; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.tenant ENABLE ROW LEVEL SECURITY;
-- Name: tenant tenant_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY tenant_aislamiento ON modulo1.tenant USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- Name: tenant tenant_lectura_sistema; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY tenant_lectura_sistema ON modulo1.tenant FOR SELECT TO modulo1_owner USING (true);
-- Name: usuario; Type: ROW SECURITY; Schema: modulo1; Owner: -
ALTER TABLE modulo1.usuario ENABLE ROW LEVEL SECURITY;
-- Name: usuario usuario_aislamiento; Type: POLICY; Schema: modulo1; Owner: -
CREATE POLICY usuario_aislamiento ON modulo1.usuario USING ((tenant_id = (current_setting('app.current_tenant'::text))::uuid)) WITH CHECK ((tenant_id = (current_setting('app.current_tenant'::text))::uuid));
-- PostgreSQL database dump complete
