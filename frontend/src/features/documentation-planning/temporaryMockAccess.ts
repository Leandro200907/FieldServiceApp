import type {
  BacklogQuery,
  CalendarQuery,
  CalendarioVigenciasResponse,
  DocumentationPlanningAccess,
  ItemBacklog,
  ItemCalendario,
  ProjectionDetailQuery,
  ProyeccionDocumentalBacklogResponse,
  ProyeccionDocumentalResponse,
} from './contracts';

// Mock de desarrollo (`VITE_ENABLE_MOCKS=true`) con la FORMA REAL del contrato — no una
// forma propia. Sirve para explorar layout sin backend; nunca decide reglas de dominio
// (los estados/capacidades de abajo son ejemplos fijos, no un cálculo). Se usa sólo cuando
// `featureFlags.documentationCalendarIntegration`/`backlogDocumentationIntegration` están
// en `false` — ver `access.ts`.
const HOY = '2026-09-21';
const ADVERTENCIA = 'Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa.';

const items: ItemCalendario[] = [
  { categoria: 'documento', id: 'cal-emp-01', sujeto_id: 'empresa-001', tipo_sujeto: 'empresa', identificador_natural: 'Empresa de servicios', requisito_definicion_id: 'req-registro-proveedor', requisito: 'Registro de proveedor', vigente_desde: '2026-09-01', vigente_hasta: '2026-10-18', estado_confirmacion: 'verificado', archivo_validacion: 'valido', dias_para_vencer: 27 },
  { categoria: 'documento', id: 'cal-per-01', sujeto_id: 'persona-marina', tipo_sujeto: 'persona', identificador_natural: 'Marina López', requisito_definicion_id: 'req-apto-medico', requisito: 'Apto médico', vigente_desde: '2026-08-01', vigente_hasta: '2026-09-27', estado_confirmacion: 'verificado', archivo_validacion: 'valido', dias_para_vencer: 6 },
  { categoria: 'induccion', id: 'cal-per-02', sujeto_id: 'persona-diego', tipo_sujeto: 'persona', identificador_natural: 'Diego Suárez', requisito_definicion_id: 'req-induccion-locacion', requisito: 'Inducción de locación', vigente_desde: '2026-08-18', vigente_hasta: '2026-09-17', estado_confirmacion: 'verificado', archivo_validacion: null, dias_para_vencer: -4 },
  { categoria: 'documento', id: 'cal-veh-01', sujeto_id: 'vehiculo-vx23', tipo_sujeto: 'vehiculo', identificador_natural: 'Unidad VX-23', requisito_definicion_id: 'req-vtv', requisito: 'VTV', vigente_desde: '2026-08-01', vigente_hasta: '2026-09-20', estado_confirmacion: 'confirmado_en_fuente', archivo_validacion: 'invalido', dias_para_vencer: -1 },
  { categoria: 'competencia', id: 'cal-eqp-01', sujeto_id: 'equipo-eq144', tipo_sujeto: 'equipo', identificador_natural: 'Detector multigás EQ-144', requisito_definicion_id: 'req-calibracion-informada', requisito: 'Calibración informada', vigente_desde: '2026-09-15', vigente_hasta: '2026-10-12', estado_confirmacion: 'declarado', archivo_validacion: null, dias_para_vencer: 21 },
  { categoria: 'documento', id: 'cal-eqp-02', sujeto_id: 'equipo-eq087', tipo_sujeto: 'equipo', identificador_natural: 'Medidor de presión EQ-087', requisito_definicion_id: 'req-certificado-calibracion', requisito: 'Certificado de calibración', vigente_desde: '2026-08-21', vigente_hasta: '2026-10-25', estado_confirmacion: 'verificado', archivo_validacion: 'pendiente', dias_para_vencer: 34 },
];

const backlogItems: ItemBacklog[] = [
  { commitment_id: 'OC-45000218', vigencia_desde: '2026-09-24', vigencia_hasta: '2026-09-30', estado: 'sin_riesgos_detectados', primer_quiebre: null, capacidad_documental_potencial_hoy: { persona: 12, vehiculo: 4, equipo: 9 }, origen_calculo: 'ultima_decision_visible', motivos_resumidos: [] },
  { commitment_id: 'OC-45000221', vigencia_desde: '2026-09-27', vigencia_hasta: '2026-10-04', estado: 'riesgo_documental', primer_quiebre: '2026-09-29', capacidad_documental_potencial_hoy: { persona: 7, vehiculo: 2 }, origen_calculo: 'ultima_decision_visible', motivos_resumidos: ['Apto médico: persona_0077 vence el 2026-09-29 sin candidato de respaldo detrás.'] },
  { commitment_id: 'OC-45000224', vigencia_desde: '2026-09-22', vigencia_hasta: '2026-09-26', estado: 'bloqueo_confirmado', primer_quiebre: '2026-09-22', capacidad_documental_potencial_hoy: { persona: 0, vehiculo: 1 }, origen_calculo: 'ultima_decision_visible', motivos_resumidos: ['VTV: ningún candidato de tipo vehiculo lo cubre en este tramo.'] },
  { commitment_id: 'OC-45000231', vigencia_desde: '2026-10-01', vigencia_hasta: '2026-10-06', estado: 'pendiente_de_planificacion', primer_quiebre: null, capacidad_documental_potencial_hoy: {}, origen_calculo: 'candidatos_del_alcance', motivos_resumidos: ['No hay decisión visible para esta OC ni candidatos en el alcance de quien consulta'] },
  { commitment_id: 'OC-45000236', vigencia_desde: '2026-10-05', vigencia_hasta: '2026-10-10', estado: 'sin_matriz', primer_quiebre: null, capacidad_documental_potencial_hoy: {}, origen_calculo: 'candidatos_del_alcance', motivos_resumidos: ['No hay matriz vigente para (cliente_id, locacion_id, tipo_servicio_id) al día de ingreso de la OC'] },
  { commitment_id: 'OC-45000240', vigencia_desde: '2026-10-12', vigencia_hasta: '2026-10-18', estado: 'requiere_revision', primer_quiebre: '2026-10-12', capacidad_documental_potencial_hoy: { persona: 3, vehiculo: 1 }, origen_calculo: 'ultima_decision_visible', motivos_resumidos: ['Inducción de locación: depende de un documento que requiere revisión, no se cuenta como cobertura real.'] },
];

const detailByCommitment = new Map<string, ProyeccionDocumentalResponse>(
  backlogItems.map(row => {
    // `intervalos[].estado` sólo admite el subconjunto de 3 (docs/PROYECCION_DOCUMENTAL.md
    // §6) — nunca los 3 exclusivos de resumen (`sin_matriz`/`pendiente_de_planificacion`/
    // `riesgo_documental`). Mapeo explícito y exhaustivo, no un cast.
    let intervalos: ProyeccionDocumentalResponse['intervalos'] = [];
    if (row.estado === 'bloqueo_confirmado' || row.estado === 'requiere_revision' || row.estado === 'sin_riesgos_detectados') {
      intervalos = [{ desde: row.vigencia_desde, hasta: row.vigencia_hasta, estado: row.estado, capacidad_documental_potencial: row.capacidad_documental_potencial_hoy }];
    } else if (row.estado === 'riesgo_documental') {
      intervalos = [
        { desde: row.vigencia_desde, hasta: row.vigencia_desde, estado: 'sin_riesgos_detectados', capacidad_documental_potencial: row.capacidad_documental_potencial_hoy },
        { desde: row.vigencia_hasta, hasta: row.vigencia_hasta, estado: 'bloqueo_confirmado', capacidad_documental_potencial: row.capacidad_documental_potencial_hoy, causas: row.motivos_resumidos.map(motivo => ({ motivo, tipo_sujeto: null, requisito_definicion_id: null, sujetos_que_pierden_cobertura: null, sujetos_que_mantienen_cobertura: null })) },
      ];
    }
    const sinIntervalos = row.estado === 'sin_matriz' || row.estado === 'pendiente_de_planificacion';
    const detail: ProyeccionDocumentalResponse = {
      commitment_id: row.commitment_id,
      hoy: HOY,
      oc: { cliente_id: 'cliente-mock', locacion_id: 'locacion-mock', tipo_servicio_id: 'servicio-mock', vigencia_desde: row.vigencia_desde, vigencia_hasta: row.vigencia_hasta },
      desde: row.vigencia_desde,
      hasta: row.vigencia_hasta,
      sujetos: { origen: row.origen_calculo, referencia_evaluacion: row.origen_calculo === 'ultima_decision_visible' ? `ref-${row.commitment_id}` : null, evaluada_en: row.origen_calculo === 'ultima_decision_visible' ? '2026-09-15T10:00:00Z' : null, sujeto_ids: [] },
      matriz: row.estado === 'sin_matriz' ? null : { matriz_version_id: `matriz-${row.commitment_id}`, version: 1, tipos_exigidos: Object.keys(row.capacidad_documental_potencial_hoy) },
      estado: row.estado,
      intervalos,
      causas: sinIntervalos && row.motivos_resumidos[0]
        ? [{ motivo: row.motivos_resumidos[0], tipo_sujeto: null, requisito_definicion_id: null, sujetos_que_pierden_cobertura: null, sujetos_que_mantienen_cobertura: null }]
        : undefined,
      advertencia: ADVERTENCIA,
    };
    return [row.commitment_id, detail];
  }),
);

// F-02 (auditoría externa 2026-09-22): el mock filtraba por SOLAPAMIENTO de vigencia
// (cualquier ítem vigente durante el rango). El backend real filtra
// `vigente_hasta BETWEEN :desde AND :hasta` — sólo lo que VENCE en el rango
// (docs/PROYECCION_DOCUMENTAL.md §3, `app/modules/proyeccion/servicio.py`). Con el
// filtro viejo, al prender el flag el calendario cambiaba de semántica (o se vaciaba)
// sin que el mock lo hubiera anticipado.
function withinRange(item: ItemCalendario, from: string, to: string) {
  return item.vigente_hasta >= from && item.vigente_hasta <= to;
}

export const temporaryMockAccess: DocumentationPlanningAccess = {
  async readCalendar(query: CalendarQuery): Promise<CalendarioVigenciasResponse> {
    const filtered = items.filter(item => withinRange(item, query.from, query.to) && (!query.subjectKind || item.tipo_sujeto === query.subjectKind));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return {
      hoy: HOY, desde: query.from, hasta: query.to,
      items: filtered.slice(offset, offset + limit),
      total: filtered.length, offset, limit,
      advertencia: ADVERTENCIA,
    };
  },
  async readBacklogProjection(query: BacklogQuery): Promise<ProyeccionDocumentalBacklogResponse> {
    const filtered = backlogItems.filter(row => !query.estado || query.estado.includes(row.estado));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return {
      hoy: HOY, horizonte_dias: query.horizonteDias ?? 30,
      items: filtered.slice(offset, offset + limit),
      total: filtered.length, offset, limit,
      advertencia: ADVERTENCIA,
    };
  },
  async readProjectionDetail(query: ProjectionDetailQuery): Promise<ProyeccionDocumentalResponse> {
    const detail = detailByCommitment.get(query.commitmentId);
    if (!detail) throw new Error('El mock temporal no contiene el detalle solicitado.');
    return detail;
  },
};
