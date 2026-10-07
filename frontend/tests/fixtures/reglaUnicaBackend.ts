/** Respuestas de ejemplo alineadas al contrato OpenAPI (valores fijos para tests de pantalla). */
import type { components } from '../../src/api/generated/modulo1';

export const HOY_TENANT = '2026-09-18';

export const legajoConsultaFixture: components['schemas']['app__modules__consultas__router__LegajoResponse'] = {
  hoy: HOY_TENANT,
  legajo: {
    legajo_id: 'persona_demo',
    sujeto_id: 'persona_demo',
    tipo_sujeto: 'persona',
    identificador_natural: '30.111.222',
    nombre_apellido: 'María Demo',
    creado_en: '2026-01-01T10:00:00Z',
    dado_de_baja_en: null,
  },
  documentos: [
    {
      tipo: 'documento',
      id: 'doc-lic',
      sujeto_id: 'persona_demo',
      requisito_definicion_id: 'req-lic',
      requisito: 'Licencia',
      categoria: 'documento',
      vigente_desde: HOY_TENANT,
      vigente_hasta: '2026-11-20',
      estado_confirmacion: 'verificado',
      origen_propuesta: false,
      locacion_id: null,
      vigente_hoy: true,
      dias_para_vencer: 63,
      vencido: false,
      estado_presentacion: 'verificada',
      codigo_estado: 'verificada',
      tarjeta_exigido: 'vigentes',
      estado_fila: 'Vigente',
      estado_presentacion_explicacion: '',
      exigido_backlog: true,
      no_exigido_backlog: false,
      faltante_exigido: true,
    },
  ],
  acreditaciones: [],
  inducciones: [],
  resumen: {
    total: 1,
    vigentes_hoy: 1,
    por_vencer: 0,
    vencidos: 1,
    en_regla: 0,
    en_regla_exigidos: 2,
    exigidos: 3,
    exigidos_vencidos: 1,
    exigidos_por_vencer: 0,
    exigidos_vigentes: 2,
    exigidos_sin_documento: 0,
    sin_documento: 0,
    observados_operadora: 0,
    pendientes_revision: 2,
    proximo_vencimiento: '2026-11-20',
    ocs_afectadas: 1,
  },
};

export const miLegajoFixture: components['schemas']['MiLegajoResponse'] = {
  hoy: HOY_TENANT,
  persona: legajoConsultaFixture,
  recursos_bajo_custodia: [],
  resumen: {
    vencidos: legajoConsultaFixture.resumen.vencidos,
    por_vencer: legajoConsultaFixture.resumen.por_vencer,
    vigentes_hoy: legajoConsultaFixture.resumen.vigentes_hoy,
  },
};

export const matricesFixture: components['schemas']['MatricesResponse'] = {
  hoy: HOY_TENANT,
  items: [
    {
      matriz_version_id: 'mv-1',
      cliente_id: 'c-1',
      locacion_id: 'l-1',
      tipo_servicio_id: 'ts-1',
      version: 2,
      vigente_desde: '2026-06-01',
      vigente_hasta: null,
      vigente_hoy: true,
      fuente: 'planilla',
      autor: null,
      matriz_global_id: null,
      copiada_de_version: null,
      creado_en: '2026-06-01T09:00:00Z',
      lineas: 1,
      operadora_nombre: 'Vista',
      locacion_nombre: 'Planta Norte',
      tipo_servicio_nombre: 'Mantenimiento',
    },
  ],
  total: 1,
  offset: 0,
  limit: 50,
};

export const accionesFixture: components['schemas']['AccionesPendientesResponse'] = {
  hoy: HOY_TENANT,
  items: [
    {
      legajo_id: 'persona_lenta',
      legajo_nombre: 'Persona Lenta',
      requisito: 'Apto médico',
      tipo_sujeto: 'persona',
      fecha_limite: HOY_TENANT,
      accion_sugerida: 'Renovar documento',
      accion_sugerida_fecha: null,
      efecto: 'Por vencer · Ya bloquea',
      accion_vencida: true,
      genera_alerta_cierta: true,
      ocs_afectadas: [],
    },
  ],
  total: 1,
  offset: 0,
  limit: 50,
};

export const backlogFixture: components['schemas']['BacklogOcResponse'] = {
  hoy: HOY_TENANT,
  items: [],
  total: 0,
  offset: 0,
  limit: 50,
};

export const calendarioFixture: components['schemas']['CalendarioVigenciasResponse'] = {
  hoy: HOY_TENANT,
  desde: '2026-08-19',
  hasta: '2026-10-28',
  items: [
    {
      categoria: 'documento',
      id: 'cal-1',
      referencia: 'evidencia:documento:cal-1',
      sujeto_id: 'persona_cal',
      tipo_sujeto: 'persona',
      identificador_natural: 'PA200FG',
      requisito_definicion_id: 'req-vtv',
      requisito: 'VTV',
      vigente_desde: HOY_TENANT,
      vigente_hasta: '2026-10-08',
      estado_confirmacion: 'verificado',
      archivo_validacion: 'valido',
      dias_para_vencer: 20,
      estado_visual_calendario: 'verificada',
    },
  ],
  total: 1,
  offset: 0,
  limit: 50,
  advertencia: 'Informativo',
};

export const timelineFixture: components['schemas']['TimelineRecursosResponse'] = {
  hoy: HOY_TENANT,
  desde: '2026-08-19',
  hasta: '2026-12-17',
  items: [],
  total: 0,
  offset: 0,
  limit: 50,
};
