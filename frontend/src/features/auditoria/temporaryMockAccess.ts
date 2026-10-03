import type { AuditoriaAccess, AuditoriaQuery, EventoAuditoria, LogAuditoriaResponse } from './contracts';

// Mock de desarrollo con la FORMA REAL del contrato — mismo patrón que el resto de
// features. `tipo` usa nombres de evento reales (`app/modules/legajos/servicio.py`), no
// inventados.
const eventos: EventoAuditoria[] = [
  { id: 5, evento_id: 'evt-005', tipo: 'DocumentoConfirmado', payload: { documento_id: 'doc-marina-apto', sujeto_id: 'persona-marina', usuario_id: 'usr-responsable-01' }, ocurrido_en: '2026-09-21T16:40:00Z' },
  { id: 4, evento_id: 'evt-004', tipo: 'DocumentoRechazado', payload: { documento_id: 'doc-diego-induccion', sujeto_id: 'persona-diego', motivo: 'Sin evidencia adjunta', usuario_id: 'usr-responsable-01' }, ocurrido_en: '2026-09-21T16:38:00Z' },
  { id: 3, evento_id: 'evt-003', tipo: 'DocumentoCargado', payload: { documento_id: 'doc-vx23-vtv', sujeto_id: 'vehiculo-vx23', origen: 'planilla' }, ocurrido_en: '2026-09-21T11:12:00Z' },
  { id: 2, evento_id: 'evt-002', tipo: 'SupervisorAsignado', payload: { sujeto_id: 'persona-diego', supervisor_usuario_id: 'usr-supervisor-01', desde: '2026-09-01' }, ocurrido_en: '2026-09-01T09:00:00Z' },
  { id: 1, evento_id: 'evt-001', tipo: 'ExcepcionRegularizada', payload: { sujeto_id: 'persona-marina', requisito_definicion_id: 'req-apto-medico', usuario_id: 'usr-responsable-01' }, ocurrido_en: '2026-08-28T14:20:00Z' },
];

export const temporaryMockAccess: AuditoriaAccess = {
  async readLogAuditoria(query: AuditoriaQuery): Promise<LogAuditoriaResponse> {
    const filtered = eventos.filter(evento =>
      (!query.tipo || evento.tipo === query.tipo)
      && (!query.desde || evento.ocurrido_en >= query.desde)
      && (!query.hasta || evento.ocurrido_en <= query.hasta));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit };
  },
};
