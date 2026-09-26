import { ApiFailure, parseApiError, session } from '../../api';
import type { LegajosAccess, SujetoSearchQuery } from './contracts';

// Adaptador real — mismo patrón que mi-legajo/realMiLegajoAccess.ts y
// vencimientos/realVencimientosAccess.ts. Ambos endpoints resuelven el alcance
// (`alcance_de_sujetos`) desde el JWT; `sujeto_id` nunca se propone libremente, solo se
// elige entre lo que `searchSujetos` ya devolvió dentro del alcance del usuario.
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

export const realLegajosAccess: LegajosAccess = {
  async searchSujetos(query: SujetoSearchQuery) {
    return unwrap(session.client.GET('/v1/consultas/sujetos', {
      params: { query: { q: query.q, tipo_sujeto: query.tipoSujeto, offset: query.offset, limit: query.limit } },
    }));
  },
  async readLegajo(sujetoId: string) {
    return unwrap(session.client.GET('/v1/consultas/legajo', { params: { query: { sujeto_id: sujetoId } } }));
  },
};
