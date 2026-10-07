import { ApiFailure, parseApiError } from '../../api';
import type { components } from '../../api/generated/modulo1';

type PostResult = { data?: unknown; error?: unknown; response: Response };

export function mensajeApi(error: unknown, response: Response, requestId: string): string {
  return parseApiError(error, response, requestId).message;
}

export async function postJson(
  post: (path: string, init: { body: unknown; headers: Record<string, string> }) => Promise<PostResult>,
  path: string,
  body: unknown,
): Promise<unknown> {
  const requestId = crypto.randomUUID();
  const res = await post(path, { body, headers: { 'Idempotency-Key': crypto.randomUUID() } });
  if (res.error !== undefined || !res.response.ok) {
    throw new ApiFailure(parseApiError(res.error, res.response, requestId));
  }
  return res.data;
}

export async function copiarDefinicionGlobal(
  post: (path: string, init: { body: unknown; headers: Record<string, string> }) => Promise<PostResult>,
  body: components['schemas']['CopiarDefinicionGlobal'],
): Promise<string> {
  const requestId = crypto.randomUUID();
  const res = await post('/v1/comandos/copiar_definicion_global', { body, headers: { 'Idempotency-Key': crypto.randomUUID() } });
  if (res.response.ok && res.data) {
    return (res.data as { requisito_definicion_id: string }).requisito_definicion_id;
  }
  const detalle = parseApiError(res.error, res.response, requestId);
  if (res.response.status === 409 && detalle.code === 'definicion_duplicada') {
    const d = detalle.details as { requisito_definicion_id?: string } | null;
    if (d?.requisito_definicion_id) return d.requisito_definicion_id;
  }
  throw new ApiFailure(detalle);
}
