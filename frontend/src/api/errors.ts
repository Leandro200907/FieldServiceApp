export interface SafeApiError {
  message: string;
  code: string;
  status: number;
  requestId: string;
  referenceSource: 'server' | 'local';
  details: unknown;
}
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
function detailMessage(value: unknown): string | null {
  if (Array.isArray(value)) {
    const mensajes = value.map(item => record(item) && typeof item.mensaje === 'string' ? item.mensaje : null).filter((item): item is string => Boolean(item));
    return mensajes.length ? [...new Set(mensajes)].join(' ') : null;
  }
  if (record(value)) {
    const pares = Object.entries(value).filter(([, item]) => ['string', 'number', 'boolean'].includes(typeof item));
    return pares.length ? pares.map(([clave, item]) => `${clave.replaceAll('_', ' ')}: ${String(item)}`).join(' · ') : null;
  }
  return typeof value === 'string' && value ? value : null;
}
export function parseApiError(body: unknown, response: Pick<Response, 'status' | 'headers'>, localId: string): SafeApiError {
  const error = record(body) && record(body.error) ? body.error : null;
  const serverId = typeof error?.request_id === 'string' && error.request_id ? error.request_id : response.headers.get('X-Request-ID');
  const baseMessage = typeof error?.mensaje === 'string' ? error.mensaje : 'No se pudo completar la solicitud.';
  const details = error?.detalles ?? null;
  const explanation = response.status === 422 ? detailMessage(details) : null;
  return {
    message: explanation ? `${baseMessage} ${explanation}` : baseMessage,
    code: typeof error?.codigo === 'string' ? error.codigo : 'HTTP_ERROR',
    status: response.status,
    requestId: serverId || localId,
    referenceSource: serverId ? 'server' : 'local',
    details,
  };
}
export class ApiFailure extends Error {
  constructor(public readonly detail: SafeApiError) { super(detail.message); }
}
export const safeFailure = (error: unknown): SafeApiError => error instanceof ApiFailure ? error.detail : {
  message: 'No se pudo completar la solicitud. Verificá la conexión e iniciá sesión nuevamente.',
  code: 'TRANSPORT_ERROR', status: 0, requestId: crypto.randomUUID(), referenceSource: 'local', details: null,
};

