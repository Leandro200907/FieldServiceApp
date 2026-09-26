import { ApiFailure, parseApiError, session } from '../../api';
import type { MiLegajoAccess } from './contracts';

// Adaptador real — mismo patrón que documentation-planning/realDocumentationPlanningAccess.ts:
// `GET /v1/consultas/mi_legajo` no recibe ningún parámetro de alcance/rol/sujeto_id — el
// servidor resuelve todo desde `identidad.sujeto_id` del JWT (nunca un id que el cliente
// elija). `openapi-fetch` no lanza en errores HTTP; se traduce siempre a `ApiFailure`.
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

export const realMiLegajoAccess: MiLegajoAccess = {
  async readMiLegajo() {
    return unwrap(session.client.GET('/v1/consultas/mi_legajo'));
  },
};
