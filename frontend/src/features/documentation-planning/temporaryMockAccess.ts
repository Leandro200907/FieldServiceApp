import type {
  BacklogQuery,
  CalendarQuery,
  CalendarioVigenciasResponse,
  DetalleLegajoRadarResponse,
  DetalleOcRadarResponse,
  DocumentationPlanningAccess,
  ItemCalendario,
  ItemRadar,
  RadarBacklogResponse,
  RadarLegajoQuery,
  RadarOcQuery,
} from './contracts';

const HOY = '2026-09-26';
const ADVERTENCIA = 'Resultado informativo calculado con los datos registrados. No garantiza disponibilidad ni asignación operativa.';

const calendarItems: ItemCalendario[] = [
  { categoria: 'documento', id: 'cal-emp-01', referencia: 'evidencia:documento:cal-emp-01', sujeto_id: 'empresa-001', tipo_sujeto: 'empresa', identificador_natural: 'Empresa de servicios', requisito_definicion_id: 'req-registro-proveedor', requisito: 'Registro de proveedor', vigente_desde: '2026-09-01', vigente_hasta: '2026-10-18', estado_confirmacion: 'verificado', archivo_validacion: 'valido', dias_para_vencer: 22 },
  { categoria: 'documento', id: 'cal-per-01', referencia: 'evidencia:documento:cal-per-01', sujeto_id: 'persona-marina', tipo_sujeto: 'persona', identificador_natural: 'Marina López', requisito_definicion_id: 'req-apto-medico', requisito: 'Apto médico', vigente_desde: '2026-08-01', vigente_hasta: '2026-09-27', estado_confirmacion: 'verificado', archivo_validacion: 'valido', dias_para_vencer: 1 },
  { categoria: 'induccion', id: 'cal-per-02', referencia: 'evidencia:induccion:cal-per-02', sujeto_id: 'persona-diego', tipo_sujeto: 'persona', identificador_natural: 'Diego Suárez', requisito_definicion_id: 'req-induccion-locacion', requisito: 'Inducción de locación', vigente_desde: '2026-08-18', vigente_hasta: '2026-09-17', estado_confirmacion: 'verificado', archivo_validacion: null, dias_para_vencer: -9 },
  { categoria: 'competencia', id: 'cal-eqp-01', referencia: 'evidencia:competencia:cal-eqp-01', sujeto_id: 'equipo-eq144', tipo_sujeto: 'equipo', identificador_natural: 'Detector multigás EQ-144', requisito_definicion_id: 'req-calibracion', requisito: 'Calibración', vigente_desde: '2026-09-15', vigente_hasta: '2026-10-12', estado_confirmacion: 'declarado', archivo_validacion: null, dias_para_vencer: 16 },
];

const radarItems: ItemRadar[] = [
  { oc_id: '11111111-1111-1111-1111-111111111111', clave_origen: 'OC-45000218', referencia: 'Servicio Norte', cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-01', tipo_servicio_id: 'mantenimiento', vigencia_desde: '2026-09-28', vigencia_hasta: '2026-10-02', estado_documental: 'sin_alertas_documentales', primer_quiebre: null, resumen: { empresa: { total: 1, con_alertas: 0, incompletos: 0 }, personas: { total: 8, con_alertas: 0, incompletos: 0 }, vehiculos: { total: 3, con_alertas: 0, incompletos: 0 }, equipos: { total: 5, con_alertas: 0, incompletos: 0 } }, motivos_resumidos: [], tiene_alertas: false },
  { oc_id: '22222222-2222-2222-2222-222222222222', clave_origen: 'OC-45000221', referencia: 'Parada programada', cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-01', tipo_servicio_id: 'inspeccion', vigencia_desde: '2026-10-03', vigencia_hasta: '2026-10-09', estado_documental: 'con_alertas_documentales', primer_quiebre: '2026-10-05', resumen: { empresa: { total: 1, con_alertas: 0, incompletos: 0 }, personas: { total: 8, con_alertas: 2, incompletos: 0 }, vehiculos: { total: 3, con_alertas: 1, incompletos: 0 }, equipos: { total: 5, con_alertas: 0, incompletos: 0 } }, motivos_resumidos: ['2 personas con alertas documentales', '1 vehiculo con alertas documentales'], tiene_alertas: true },
  { oc_id: '33333333-3333-3333-3333-333333333333', clave_origen: 'OC-45000224', referencia: null, cliente_id: 'cliente-sur', locacion_id: 'locacion-sur-02', tipo_servicio_id: 'calibracion', vigencia_desde: '2026-10-12', vigencia_hasta: '2026-10-15', estado_documental: 'informacion_incompleta', primer_quiebre: null, resumen: { empresa: { total: 1, con_alertas: 0, incompletos: 0 }, personas: { total: 4, con_alertas: 0, incompletos: 1 }, vehiculos: { total: 1, con_alertas: 0, incompletos: 0 }, equipos: { total: 3, con_alertas: 0, incompletos: 1 } }, motivos_resumidos: [], tiene_alertas: false },
  { oc_id: '44444444-4444-4444-4444-444444444444', clave_origen: 'OC-45000236', referencia: 'Servicio nuevo', cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-03', tipo_servicio_id: 'mantenimiento', vigencia_desde: '2026-10-20', vigencia_hasta: '2026-10-22', estado_documental: 'sin_matriz', primer_quiebre: null, resumen: { empresa: { total: 1, con_alertas: 0, incompletos: 0 }, personas: { total: 0, con_alertas: 0, incompletos: 0 }, vehiculos: { total: 0, con_alertas: 0, incompletos: 0 }, equipos: { total: 0, con_alertas: 0, incompletos: 0 } }, motivos_resumidos: [], tiene_alertas: false },
];

function radarDetail(item: ItemRadar, offset = 0, limit = 50): DetalleOcRadarResponse {
  const mockLegajos = [{
    sujeto_id: 'persona-marina',
    tipo_sujeto: 'persona',
    nombre_apellido: 'María González',
    identificador_natural: '30.111.222',
    estado_documental: item.estado_documental,
    primer_quiebre: item.primer_quiebre,
    requisitos: [
      {
        nombre: 'Apto médico',
        estado: 'vigente_todo_el_periodo',
        vigente_hasta: '2026-12-01',
        motivo: 'Apto médico está vigente durante todo el período',
        archivo_validacion: 'valido',
        requerido: true,
      },
      {
        nombre: 'Licencia de conducir',
        estado: 'vence_durante_periodo',
        vigente_hasta: '2026-10-08',
        motivo: 'Licencia de conducir deja un período sin cobertura documental',
        archivo_validacion: 'valido',
        requerido: true,
      },
      {
        nombre: 'Constancia ART',
        estado: 'pendiente_revision',
        vigente_hasta: '2026-11-30',
        motivo: 'Constancia ART tiene información pendiente de revisión',
        archivo_validacion: 'pendiente',
        requerido: true,
      },
      {
        nombre: 'Inducción operadora',
        estado: 'pendiente_revision',
        vigente_hasta: '2026-11-15',
        motivo: 'Inducción operadora tiene información pendiente de revisión',
        archivo_validacion: 'sin_archivo',
        requerido: true,
      },
    ],
  }];
  return {
    oc: { oc_id: item.oc_id, clave_origen: item.clave_origen, referencia: item.referencia, vigencia_desde: item.vigencia_desde, vigencia_hasta: item.vigencia_hasta },
    estado_documental: item.estado_documental,
    matrices_utilizadas: item.estado_documental === 'sin_matriz' ? [] : [{ version: 3, desde: item.vigencia_desde, hasta: item.vigencia_hasta }],
    requisitos_particulares: [],
    huecos_matriz: item.estado_documental === 'sin_matriz' ? [{ desde: item.vigencia_desde, hasta: item.vigencia_hasta }] : [],
    grupos: [
      { tipo_sujeto: 'persona', requerido: true, sin_legajos_requeridos: false, total: mockLegajos.length, offset, limit, legajos: mockLegajos.slice(offset, offset + limit) },
    ],
    total_legajos: mockLegajos.length,
    offset,
    limit,
    advertencia: ADVERTENCIA,
    tiene_alertas: item.estado_documental === 'con_alertas_documentales',
  };
}

function withinRange(item: ItemCalendario, from: string, to: string) {
  return item.vigente_hasta >= from && item.vigente_hasta <= to;
}

export const temporaryMockAccess: DocumentationPlanningAccess = {
  async readCalendar(query: CalendarQuery): Promise<CalendarioVigenciasResponse> {
    const filtered = calendarItems.filter(item => withinRange(item, query.from, query.to) && (!query.subjectKind || item.tipo_sujeto === query.subjectKind) && (!query.q || item.identificador_natural?.toLowerCase().includes(query.q.toLowerCase())));
    const offset = query.offset ?? 0; const limit = query.limit ?? 50;
    return { hoy: HOY, desde: query.from, hasta: query.to, items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit, advertencia: ADVERTENCIA };
  },
  async readRadarBacklog(query: BacklogQuery): Promise<RadarBacklogResponse> {
    const filtered = radarItems.filter(item =>
      (!query.estado || query.estado.includes(item.estado_documental))
      && (!query.q || `${item.clave_origen} ${item.referencia ?? ''}`.toLowerCase().includes(query.q.toLowerCase()))
      && (!query.from || item.vigencia_hasta >= query.from)
      && (!query.to || item.vigencia_desde <= query.to));
    const offset = query.offset ?? 0; const limit = query.limit ?? 50;
    return { calculado_en: `${HOY}T12:00:00Z`, desde: query.from ?? HOY, hasta: query.to ?? '2026-11-25', items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit, advertencia: ADVERTENCIA };
  },
  async readRadarOc(query: RadarOcQuery): Promise<DetalleOcRadarResponse> {
    const item = radarItems.find(row => row.oc_id === query.ocId);
    if (!item) throw new Error('El mock temporal no contiene la OC solicitada.');
    return radarDetail(item, query.offset, query.limit);
  },
  async readRadarLegajo(query: RadarLegajoQuery): Promise<DetalleLegajoRadarResponse> {
    const detail = await temporaryMockAccess.readRadarOc({ ocId: query.ocId });
    const legajos = detail.grupos.flatMap(group => Array.isArray(group.legajos) ? group.legajos : []);
    const legajo = legajos.find(candidate => candidate && typeof candidate === 'object' && candidate.sujeto_id === query.sujetoId);
    if (!legajo || typeof legajo !== 'object') throw new Error('El mock temporal no contiene el legajo solicitado.');
    return { oc: detail.oc, legajo, advertencia: ADVERTENCIA };
  },
};

