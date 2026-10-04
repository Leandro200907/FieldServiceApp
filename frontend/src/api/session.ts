import createClient from 'openapi-fetch';
import type { components, paths } from './generated/modulo1';
import { ApiFailure, parseApiError, safeFailure, type SafeApiError } from './errors';
type Identity = components['schemas']['IdentidadResponse'];
type Tokens = components['schemas']['ParDeTokens'];
export type SessionSnapshot = Readonly<{
  status: 'anonymous' | 'authenticating' | 'authenticated' | 'refreshing';
  identity: Identity | null;
  error: SafeApiError | null;
  /** Tras cerrar sesión explícita, no propagar ?return= al login. */
  suppressLoginReturn?: boolean;
}>;
interface Options { baseUrl?: string; fetch?: typeof fetch; now?: () => number; timeoutMs?: number }
const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null;
function tokens(value: unknown): Tokens {
  if (!object(value) || typeof value.access_token !== 'string' || !value.access_token || typeof value.refresh_token !== 'string' || !value.refresh_token || !Number.isInteger(value.expires_in) || Number(value.expires_in) <= 0 || (value.token_type !== undefined && value.token_type !== 'bearer')) throw new Error('Invalid tokens');
  return value as Tokens;
}
function identity(value: unknown): Identity {
  if (!object(value) || typeof value.tenant_id !== 'string' || typeof value.tenant_nombre !== 'string' || typeof value.usuario_id !== 'string' || !Array.isArray(value.roles) || !value.roles.every(role => typeof role === 'string') || !(value.sujeto_id === null || typeof value.sujeto_id === 'string') || typeof value.zona_horaria !== 'string' || !value.zona_horaria) throw new Error('Invalid identity');
  return {
    tenant_id: value.tenant_id,
    tenant_nombre: value.tenant_nombre,
    usuario_id: value.usuario_id,
    usuario_nombre: typeof value.usuario_nombre === 'string' ? value.usuario_nombre : null,
    usuario_email: typeof value.usuario_email === 'string' ? value.usuario_email : null,
    roles: [...value.roles],
    sujeto_id: value.sujeto_id,
    legajo_etiqueta: value.legajo_etiqueta === null || typeof value.legajo_etiqueta === 'string' ? value.legajo_etiqueta : null,
    zona_horaria: value.zona_horaria,
  };
}
export function createSession(options: Options = {}) {
  const origin = options.baseUrl || (typeof location === 'undefined' ? 'http://localhost' : location.origin);
  const url = new URL(origin);
  if (url.pathname !== '/' || url.search || url.hash || url.username || url.password || !['http:', 'https:'].includes(url.protocol)) throw new Error('API baseUrl must be an HTTP(S) origin without /v1');
  const transport = options.fetch ?? globalThis.fetch.bind(globalThis);
  const now = options.now ?? Date.now;
  const timeoutMs = options.timeoutMs ?? 20000;
  let snapshot: SessionSnapshot = { status: 'anonymous', identity: null, error: null, suppressLoginReturn: false };
  let pair: Tokens | null = null;
  let deadline = 0;
  let generation = 0;
  let refreshFlight: Promise<void> | null = null;
  const listeners = new Set<() => void>();
  const controllers = new Set<AbortController>();
  function publish(value: SessionSnapshot) { snapshot = Object.freeze(value); listeners.forEach(listener => listener()); }
  function clear(error: SafeApiError | null = null, opts?: { suppressLoginReturn?: boolean }) {
    generation++; pair = null; deadline = 0; refreshFlight = null;
    controllers.forEach(controller => controller.abort()); controllers.clear();
    publish({
      status: 'anonymous',
      identity: null,
      error,
      suppressLoginReturn: Boolean(opts?.suppressLoginReturn),
    });
  }
  function check(version: number) { if (version !== generation) throw new DOMException('Session changed', 'AbortError'); }
  async function raw(path: '/v1/auth/login' | '/v1/auth/refresh' | '/v1/auth/logout' | '/v1/auth/yo', body?: unknown, bearer?: string): Promise<unknown> {
    const controller = new AbortController(); controllers.add(controller);
    const requestId = crypto.randomUUID();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await transport(`${url.origin}${path}`, { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Request-ID': requestId, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, cache: 'no-store', credentials: 'omit' });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new ApiFailure(parseApiError(payload, response, requestId));
      return payload;
    } finally { clearTimeout(timer); controllers.delete(controller); }
  }
  async function login(body: components['schemas']['LoginRequest']) {
    clear(null, { suppressLoginReturn: false }); const version = generation;
    publish({ status: 'authenticating', identity: null, error: null });
    try {
      const next = tokens(await raw('/v1/auth/login', body)); check(version);
      const expiresAt = now() + next.expires_in * 1000;
      const who = identity(await raw('/v1/auth/yo', undefined, next.access_token)); check(version);
      pair = next; deadline = expiresAt;
      publish({ status: 'authenticated', identity: who, error: null });
    } catch (error) { if (version === generation) clear(safeFailure(error)); }
  }
  function refresh(): Promise<void> {
    if (refreshFlight) return refreshFlight;
    if (!pair) return Promise.reject(new Error('No session'));
    const version = generation; const current = pair;
    publish({ ...snapshot, status: 'refreshing', error: null });
    const pending = (async () => {
      try {
        const next = tokens(await raw('/v1/auth/refresh', { refresh_token: current.refresh_token })); check(version);
        const expiresAt = now() + next.expires_in * 1000;
        const who = identity(await raw('/v1/auth/yo', undefined, next.access_token)); check(version);
        pair = next; deadline = expiresAt;
        publish({ status: 'authenticated', identity: who, error: null });
      } catch (error) {
        if (version === generation) {
          const failure = safeFailure(error);
          if (failure.status === 0) publish({ ...snapshot, status: 'authenticated', error: failure });
          else clear(failure);
        }
        throw error;
      }
    })();
    refreshFlight = pending;
    void pending.finally(() => { if (refreshFlight === pending) refreshFlight = null; }).catch(() => {});
    return pending;
  }
  async function authorizedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const request = new Request(input, init);
    const target = new URL(request.url);
    const signedBlobOnly = target.pathname.startsWith('/v1/storage/') && !target.pathname.startsWith('/v1/storage/documentos/');
    if (target.origin !== url.origin || !target.pathname.startsWith('/v1/') || signedBlobOnly || ['/v1/auth/login', '/v1/auth/refresh', '/v1/auth/logout'].includes(target.pathname)) throw new Error('Use the dedicated transport for this endpoint');
    const version = generation;
    if (!pair) throw new Error('No session');
    const margin = Math.min(5000, pair.expires_in * 100);
    if (refreshFlight || now() >= deadline - margin) await (refreshFlight ?? refresh());
    check(version);
    if (!pair) throw new Error('No session');
    const controller = new AbortController(); controllers.add(controller);
    const abort = () => controller.abort(); request.signal.addEventListener('abort', abort, { once: true });
    if (request.signal.aborted) controller.abort();
    const headers = new Headers(request.headers); headers.set('Authorization', `Bearer ${pair.access_token}`);
    const requestId = crypto.randomUUID(); headers.set('X-Request-ID', requestId);
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await transport(new Request(request, { headers, signal: controller.signal, cache: 'no-store', credentials: 'omit' })); check(version);
      if (response.status === 401) {
        const error = parseApiError(await response.clone().json().catch(() => null), response, requestId);
        clear(error); throw new ApiFailure(error);
      }
      return response;
    } finally { clearTimeout(timer); controllers.delete(controller); request.signal.removeEventListener('abort', abort); }
  }
  async function logout() {
    const current = pair; clear(null, { suppressLoginReturn: true }); const version = generation;
    if (!current) return;
    try { await raw('/v1/auth/logout', { refresh_token: current.refresh_token }, current.access_token); }
    catch {
      if (version === generation) {
        publish({
          status: 'anonymous',
          identity: null,
          suppressLoginReturn: true,
          error: {
            message: 'Sesión cerrada en este dispositivo; no se pudo confirmar la revocación.',
            code: 'LOGOUT_UNCONFIRMED',
            status: 0,
            requestId: crypto.randomUUID(),
            referenceSource: 'local',
            details: null,
          },
        });
      }
    }
  }
  return { subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; }, getSnapshot: () => snapshot, login, logout, refresh, client: createClient<paths>({ baseUrl: url.origin, fetch: authorizedFetch }) };
}

