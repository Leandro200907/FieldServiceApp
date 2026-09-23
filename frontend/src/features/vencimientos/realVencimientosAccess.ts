import { ApiFailure, parseApiError, session } from '../../api';
import type { VencimientosAccess, VencimientosQuery } from './contracts';

// Adaptador real — mismo patrón que mi-legajo/realMiLegajoAccess.ts. `GET
// /v1/consultas/tablero_vencimientos` resuelve el alcance (empresa completa para
// responsable_legajos, universo propio para supervisor) desde `identidad` en el JWT; el
// cliente solo pasa `dias`/`offset`/`limit`.
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

export const realVencimientosAccess: VencimientosAccess = {
  async readTableroVencimientos(query: VencimientosQuery) {
    return unwrap(session.client.GET('/v1/consultas/tablero_vencimientos', {
      params: { query: { dias: query.dias, offset: query.offset, limit: query.limit } },
    }));
  },
};
