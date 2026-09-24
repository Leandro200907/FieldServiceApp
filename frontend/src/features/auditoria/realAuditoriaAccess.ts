import { ApiFailure, parseApiError, session } from '../../api';
import type { AuditoriaAccess, AuditoriaQuery } from './contracts';

// Adaptador real — mismo patrón que el resto de features de solo lectura
// (vencimientos/legajos). El alcance (tenant completo) lo resuelve el servidor por rol.
async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

export const realAuditoriaAccess: AuditoriaAccess = {
  async readLogAuditoria(query: AuditoriaQuery) {
    return unwrap(session.client.GET('/v1/consultas/log_auditoria', {
      params: { query: { tipo: query.tipo, desde: query.desde, hasta: query.hasta, offset: query.offset, limit: query.limit } },
    }));
  },
};
