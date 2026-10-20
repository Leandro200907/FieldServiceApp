import { ApiFailure, parseApiError, session } from '../../api';
import { createCommandIntent } from '../../api/idempotency';
import type { components } from '../../api/generated/modulo1';

type AltaDeSujeto = components['schemas']['AltaDeSujeto'];

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

export async function altaDeSujeto(body: AltaDeSujeto) {
  const intent = createCommandIntent('/v1/comandos/alta_de_sujeto', body);
  return unwrap(session.client.POST('/v1/comandos/alta_de_sujeto', { body, headers: intent.headers }));
}
