import type { EvidenciaVigente, LegajoLookupResponse, LegajosAccess, SujetoItem, SujetoSearchQuery, SujetosResponse } from './contracts';

// Mock de desarrollo con la FORMA REAL del contrato — mismo patrón que
// mi-legajo/temporaryMockAccess.ts y vencimientos/temporaryMockAccess.ts. Se usa solo
// mientras `featureFlags.legajoLookupIntegration` está en `false` (ver access.ts).
const HOY = '2026-09-21';

const sujetos: SujetoItem[] = [
  { sujeto_id: 'persona-marina', tipo_sujeto: 'persona', identificador_natural: 'Marina López', dado_de_baja_en: null, creado_en: '2026-01-10T09:00:00Z' },
  { sujeto_id: 'persona-diego', tipo_sujeto: 'persona', identificador_natural: 'Diego Suárez', dado_de_baja_en: null, creado_en: '2026-01-12T09:00:00Z' },
  { sujeto_id: 'vehiculo-vx23', tipo_sujeto: 'vehiculo', identificador_natural: 'Unidad VX-23', dado_de_baja_en: null, creado_en: '2026-02-01T09:00:00Z' },
  { sujeto_id: 'equipo-eq144', tipo_sujeto: 'equipo', identificador_natural: 'Detector multigás EQ-144', dado_de_baja_en: null, creado_en: '2026-02-15T09:00:00Z' },
  { sujeto_id: 'empresa-001', tipo_sujeto: 'empresa', identificador_natural: 'Empresa de servicios', dado_de_baja_en: null, creado_en: '2026-01-01T09:00:00Z' },
];

function evidencia(id: string, sujeto_id: string, requisito: string, categoria: string, hasta: string, dias: number): EvidenciaVigente {
  return { tipo: categoria, id, sujeto_id, requisito_definicion_id: `req-${id}`, requisito, categoria, vigente_desde: '2026-08-01', vigente_hasta: hasta, estado_confirmacion: dias < 0 ? 'confirmado_en_fuente' : 'verificado', origen_propuesta: false, locacion_id: null, vigente_hoy: dias >= 0, dias_para_vencer: dias, vencido: dias < 0 };
}

const legajosPorSujeto: Record<string, LegajoLookupResponse> = {
  'persona-marina': {
    hoy: HOY,
    legajo: { legajo_id: 'legajo-marina', sujeto_id: 'persona-marina', tipo_sujeto: 'persona', identificador_natural: 'Marina López', dado_de_baja_en: null, creado_en: '2026-01-10T09:00:00Z' },
    documentos: [evidencia('leg-mar-01', 'persona-marina', 'Apto médico', 'documento', '2026-09-27', 6)],
    acreditaciones: [], inducciones: [],
    resumen: { total: 1, vigentes_hoy: 1, vencidos: 0 },
  },
  'persona-diego': {
    hoy: HOY,
    legajo: { legajo_id: 'legajo-diego', sujeto_id: 'persona-diego', tipo_sujeto: 'persona', identificador_natural: 'Diego Suárez', dado_de_baja_en: null, creado_en: '2026-01-12T09:00:00Z' },
    documentos: [], acreditaciones: [], inducciones: [evidencia('leg-dgo-01', 'persona-diego', 'Inducción de locación', 'induccion', '2026-09-17', -4)],
    resumen: { total: 1, vigentes_hoy: 0, vencidos: 1 },
  },
  'vehiculo-vx23': {
    hoy: HOY,
    legajo: { legajo_id: 'legajo-vx23', sujeto_id: 'vehiculo-vx23', tipo_sujeto: 'vehiculo', identificador_natural: 'Unidad VX-23', dado_de_baja_en: null, creado_en: '2026-02-01T09:00:00Z' },
    documentos: [evidencia('leg-vx23-01', 'vehiculo-vx23', 'VTV', 'documento', '2026-09-20', -1)],
    acreditaciones: [], inducciones: [],
    resumen: { total: 1, vigentes_hoy: 0, vencidos: 1 },
  },
  'equipo-eq144': {
    hoy: HOY,
    legajo: { legajo_id: 'legajo-eq144', sujeto_id: 'equipo-eq144', tipo_sujeto: 'equipo', identificador_natural: 'Detector multigás EQ-144', dado_de_baja_en: null, creado_en: '2026-02-15T09:00:00Z' },
    documentos: [], acreditaciones: [evidencia('leg-eq144-01', 'equipo-eq144', 'Calibración informada', 'competencia', '2026-10-12', 21)], inducciones: [],
    resumen: { total: 1, vigentes_hoy: 1, vencidos: 0 },
  },
  'empresa-001': {
    hoy: HOY,
    legajo: { legajo_id: 'legajo-empresa', sujeto_id: 'empresa-001', tipo_sujeto: 'empresa', identificador_natural: 'Empresa de servicios', dado_de_baja_en: null, creado_en: '2026-01-01T09:00:00Z' },
    documentos: [evidencia('leg-emp-01', 'empresa-001', 'Registro de proveedor', 'documento', '2026-10-18', 27)],
    acreditaciones: [], inducciones: [],
    resumen: { total: 1, vigentes_hoy: 1, vencidos: 0 },
  },
};

export const temporaryMockAccess: LegajosAccess = {
  async searchSujetos(query: SujetoSearchQuery): Promise<SujetosResponse> {
    const q = query.q?.trim().toLowerCase();
    const filtered = sujetos.filter(sujeto =>
      (!q || sujeto.identificador_natural.toLowerCase().includes(q) || sujeto.sujeto_id.toLowerCase().includes(q))
      && (!query.tipoSujeto || sujeto.tipo_sujeto === query.tipoSujeto));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit };
  },
  async readLegajo(sujetoId: string): Promise<LegajoLookupResponse> {
    const legajo = legajosPorSujeto[sujetoId];
    if (!legajo) throw new Error('El mock temporal no contiene el legajo solicitado.');
    return legajo;
  },
};
