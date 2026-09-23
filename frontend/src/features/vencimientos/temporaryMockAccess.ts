import type { EvidenciaVigente, TableroVencimientosResponse, VencimientosAccess, VencimientosQuery } from './contracts';

// Mock de desarrollo con la FORMA REAL del contrato — mismo patrón que
// documentation-planning/temporaryMockAccess.ts. Se usa solo mientras
// `featureFlags.expirationsBoardIntegration` está en `false` (ver access.ts).
const HOY = '2026-09-21';

const items: EvidenciaVigente[] = [
  { tipo: 'documento', id: 'ev-per-marina-apto', sujeto_id: 'persona-marina', requisito_definicion_id: 'req-apto-medico', requisito: 'Apto médico', categoria: 'documento', vigente_desde: '2026-08-01', vigente_hasta: '2026-09-27', estado_confirmacion: 'verificado', origen_propuesta: false, locacion_id: null, vigente_hoy: true, dias_para_vencer: 6, vencido: false },
  { tipo: 'induccion', id: 'ev-per-diego-induccion', sujeto_id: 'persona-diego', requisito_definicion_id: 'req-induccion-locacion', requisito: 'Inducción de locación', categoria: 'induccion', vigente_desde: '2026-08-18', vigente_hasta: '2026-09-17', estado_confirmacion: 'verificado', origen_propuesta: false, locacion_id: 'locacion-norte-01', vigente_hoy: false, dias_para_vencer: -4, vencido: true },
  { tipo: 'documento', id: 'ev-veh-vx23-vtv', sujeto_id: 'vehiculo-vx23', requisito_definicion_id: 'req-vtv', requisito: 'VTV', categoria: 'documento', vigente_desde: '2026-08-01', vigente_hasta: '2026-09-20', estado_confirmacion: 'confirmado_en_fuente', origen_propuesta: false, locacion_id: null, vigente_hoy: false, dias_para_vencer: -1, vencido: true },
  { tipo: 'competencia', id: 'ev-eqp-144-calibracion', sujeto_id: 'equipo-eq144', requisito_definicion_id: 'req-calibracion-informada', requisito: 'Calibración informada', categoria: 'competencia', vigente_desde: '2026-09-15', vigente_hasta: '2026-10-12', estado_confirmacion: 'declarado', origen_propuesta: true, locacion_id: null, vigente_hoy: true, dias_para_vencer: 21, vencido: false },
  { tipo: 'documento', id: 'ev-emp-registro', sujeto_id: 'empresa-001', requisito_definicion_id: 'req-registro-proveedor', requisito: 'Registro de proveedor', categoria: 'documento', vigente_desde: '2026-09-01', vigente_hasta: '2026-10-18', estado_confirmacion: 'verificado', origen_propuesta: false, locacion_id: null, vigente_hoy: true, dias_para_vencer: 27, vencido: false },
];

export const temporaryMockAccess: VencimientosAccess = {
  async readTableroVencimientos(query: VencimientosQuery): Promise<TableroVencimientosResponse> {
    const dias = query.dias ?? 30;
    const limite = new Date(new Date(`${HOY}T12:00:00`).getTime() + dias * 86400000).toISOString().slice(0, 10);
    const filtered = items.filter(item => item.vigente_hasta <= limite);
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return {
      hoy: HOY, hasta: limite,
      items: filtered.slice(offset, offset + limit),
      total: filtered.length, offset, limit,
    };
  },
};
