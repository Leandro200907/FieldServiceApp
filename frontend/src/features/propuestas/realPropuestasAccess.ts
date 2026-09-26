import { ApiFailure, parseApiError, session } from '../../api';
import { createCommandIntent } from '../../api/idempotency';
import type { PropuestasAccess, PropuestasQuery } from './contracts';

// Adaptador real — primer feature de este frontend que ejecuta comandos de escritura
// (`POST /v1/comandos/*`), no solo lecturas. `createCommandIntent` (ya scaffoldeado en
// `src/api/idempotency.ts`, cubierto por tests/api-session.test.ts, hasta ahora sin un
// consumidor real) fija el body serializado y una `Idempotency-Key` estable ANTES de la
// llamada, para que un reintento tras un resultado de red incierto nunca duplique la
// confirmación/rechazo de un documento.
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

export const realPropuestasAccess: PropuestasAccess = {
  async readPropuestasPendientes(query: PropuestasQuery) {
    return unwrap(session.client.GET('/v1/consultas/propuestas_pendientes', {
      params: { query: { offset: query.offset, limit: query.limit } },
    }));
  },
  async confirmarDocumento(documentoId: string) {
    const intent = createCommandIntent('/v1/comandos/confirmar_documento', { documento_id: documentoId });
    return unwrap(session.client.POST('/v1/comandos/confirmar_documento', {
      body: { documento_id: documentoId }, headers: intent.headers,
    }));
  },
  async rechazarPropuesta(documentoId: string, motivo?: string) {
    const intent = createCommandIntent('/v1/comandos/rechazar_propuesta', { documento_id: documentoId, motivo: motivo ?? null });
    return unwrap(session.client.POST('/v1/comandos/rechazar_propuesta', {
      body: { documento_id: documentoId, motivo: motivo ?? null }, headers: intent.headers,
    }));
  },
};
