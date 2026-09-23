import type { ConfirmarDocumentoResponse, DocumentoPropuesto, PropuestasAccess, PropuestasPendientesResponse, PropuestasQuery, RechazarPropuestaResponse } from './contracts';

// Mock de desarrollo con la FORMA REAL del contrato — mismo patrón que el resto de
// features. A diferencia de los mocks de solo lectura, éste mantiene estado mutable en
// memoria (no persiste entre recargas) para que confirmar/rechazar realmente saquen el
// ítem de la bandeja, igual que haría el backend real.
// `origen` es `Literal["planilla", "carga_manual", "drive"]` en el backend
// (`app/modules/legajos/esquemas.py::OrigenDocumento`) — no "app_movil"; el mock usa
// exactamente esos tres valores reales.
let items: DocumentoPropuesto[] = [
  { documento_id: 'doc-marina-apto', sujeto_id: 'persona-marina', requisito_definicion_id: 'req-apto-medico', requisito: 'Apto médico', numero: 'AM-2026-0231', vigente_desde: '2026-09-01', vigente_hasta: '2026-12-01', estado_confirmacion: 'declarado', origen: 'drive', confianza_extraccion: 'alta', creado_en: '2026-09-19T14:05:00Z', vigente_hoy: true, dias_para_vencer: 71, vencido: false },
  { documento_id: 'doc-diego-induccion', sujeto_id: 'persona-diego', requisito_definicion_id: 'req-induccion-locacion', requisito: 'Inducción de locación', numero: null, vigente_desde: '2026-09-15', vigente_hasta: '2027-09-15', estado_confirmacion: 'declarado', origen: 'carga_manual', confianza_extraccion: null, creado_en: '2026-09-20T09:30:00Z', vigente_hoy: true, dias_para_vencer: 360, vencido: false },
  { documento_id: 'doc-vx23-vtv', sujeto_id: 'vehiculo-vx23', requisito_definicion_id: 'req-vtv', requisito: 'VTV', numero: 'VTV-88213', vigente_desde: '2026-09-10', vigente_hasta: '2027-03-10', estado_confirmacion: 'declarado', origen: 'planilla', confianza_extraccion: 'media', creado_en: '2026-09-21T11:12:00Z', vigente_hoy: true, dias_para_vencer: 170, vencido: false },
];

export const temporaryMockAccess: PropuestasAccess = {
  async readPropuestasPendientes(query: PropuestasQuery): Promise<PropuestasPendientesResponse> {
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: items.slice(offset, offset + limit), total: items.length, offset, limit };
  },
  async confirmarDocumento(documentoId: string): Promise<ConfirmarDocumentoResponse> {
    const item = items.find(candidate => candidate.documento_id === documentoId);
    if (!item) throw new Error('El mock temporal no contiene el documento solicitado.');
    items = items.filter(candidate => candidate.documento_id !== documentoId);
    return { documento_id: documentoId, excepciones_regularizadas: [], eventos: ['documento_confirmado'] };
  },
  async rechazarPropuesta(documentoId: string): Promise<RechazarPropuestaResponse> {
    const item = items.find(candidate => candidate.documento_id === documentoId);
    if (!item) throw new Error('El mock temporal no contiene el documento solicitado.');
    items = items.filter(candidate => candidate.documento_id !== documentoId);
    return { documento_id: documentoId, restaurado_documento_id: null, eventos: ['propuesta_rechazada'] };
  },
};
