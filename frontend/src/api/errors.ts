export interface SafeApiError {
  message: string;
  code: string;
  status: number;
  requestId: string;
  referenceSource: 'server' | 'local';
}
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
export function parseApiError(body: unknown, response: Pick<Response, 'status' | 'headers'>, localId: string): SafeApiError {
  const error = record(body) && record(body.error) ? body.error : null;
  const serverId = typeof error?.request_id === 'string' && error.request_id ? error.request_id : response.headers.get('X-Request-ID');
  return {
    message: typeof error?.mensaje === 'string' ? error.mensaje : 'No se pudo completar la solicitud.',
    code: typeof error?.codigo === 'string' ? error.codigo : 'HTTP_ERROR',
    status: response.status,
    requestId: serverId || localId,
    referenceSource: serverId ? 'server' : 'local',
  };
}
export class ApiFailure extends Error {
  constructor(public readonly detail: SafeApiError) { super(detail.message); }
}
export const safeFailure = (error: unknown): SafeApiError => error instanceof ApiFailure ? error.detail : {
  message: 'No se pudo completar la solicitud. Verificá la conexión e iniciá sesión nuevamente.',
  code: 'TRANSPORT_ERROR', status: 0, requestId: crypto.randomUUID(), referenceSource: 'local',
};
