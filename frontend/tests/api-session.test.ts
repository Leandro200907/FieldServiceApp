import { describe, expect, it, vi } from 'vitest';
import { createSession } from '../src/api/session';
import { parseApiError } from '../src/api/errors';
import { createCommandIntent } from '../src/api/idempotency';
const who = { tenant_id: 'tenant', usuario_id: 'user', roles: ['tecnico'], sujeto_id: null };
const pair = { access_token: 'access', refresh_token: 'refresh', expires_in: 60, token_type: 'bearer' };
const reply = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const login = { tenant_slug: 'tenant', email: 'user@example.com', password: 'secret' };
function fixture() {
  let time = 0;
  const mock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
    const path = typeof input === 'string' ? input : input instanceof Request ? input.url : input.href;
    return reply(path.endsWith('/yo') ? who : pair);
  });
  const session = createSession({ baseUrl: 'https://api.example.com', fetch: mock, now: () => time });
  return { session, mock, advance: () => { time = 60000; } };
}
describe('session boundary', () => {
  it('coalesces refresh and publishes new identity before waiting reads resume', async () => {
    const { session, mock, advance } = fixture(); await session.login(login); advance();
    let release!: (response: Response) => void;
    mock.mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
    const a = session.client.GET('/v1/auth/yo'); const b = session.client.GET('/v1/auth/yo');
    await vi.waitFor(() => expect(session.getSnapshot().status).toBe('refreshing'));
    release(reply({ ...pair, access_token: 'new-access' }));
    await Promise.all([a, b]);
    expect(mock.mock.calls.filter(([input]) => String(input).endsWith('/refresh'))).toHaveLength(1);
    expect(session.getSnapshot().status).toBe('authenticated');
    const reads = mock.mock.calls.map(([input]) => input).filter((input): input is Request => input instanceof Request);
    expect(reads).toHaveLength(2); expect(reads.every(request => request.headers.get('Authorization') === 'Bearer new-access')).toBe(true);
  });
  it('does not resurrect a session when refresh completes after logout', async () => {
    const { session, mock } = fixture(); await session.login(login);
    let release!: (response: Response) => void;
    mock.mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
    const refreshing = session.refresh(); const outcome = refreshing.catch(() => undefined);
    await session.logout(); release(reply(pair)); await outcome;
    expect(session.getSnapshot().status).toBe('anonymous'); expect(session.getSnapshot().identity).toBeNull();
  });
  it('clears unexpected 401 without refresh or retry', async () => {
    const { session, mock } = fixture(); await session.login(login);
    mock.mockResolvedValueOnce(reply({ error: { codigo: 'INACTIVE', mensaje: 'No autorizado', request_id: 'server-id', detalles: null } }, 401));
    await expect(session.client.GET('/v1/auth/yo')).rejects.toThrow();
    expect(mock).toHaveBeenCalledTimes(3); expect(session.getSnapshot().status).toBe('anonymous');
    expect(session.getSnapshot().error?.requestId).toBe('server-id');
  });
  it('does not enable authenticated UI before profile is validated', async () => {
    const { session, mock } = fixture(); mock.mockResolvedValueOnce(reply(pair)).mockResolvedValueOnce(reply({ roles: [] }));
    await session.login(login); expect(session.getSnapshot().status).toBe('anonymous');
  });
  it('rejects base URLs that duplicate /v1', () => { expect(() => createSession({ baseUrl: 'https://api.example.com/v1' })).toThrow(); });
});
it('parses malformed errors safely and distinguishes local references', () => {
  const response = reply({}, 500);
  expect(parseApiError({ error: { mensaje: { unsafe: true } } }, response, 'local-id')).toMatchObject({ code: 'HTTP_ERROR', referenceSource: 'local', requestId: 'local-id' });
  response.headers.set('X-Request-ID', 'header-id');
  expect(parseApiError(null, response, 'local-id').requestId).toBe('header-id');
});
it('keeps intent payload and key immutable across retries', () => {
  const body = { sujeto_id: 'real-selected-id' };
  const intent = createCommandIntent('/v1/comandos/baja_de_sujeto', body);
  body.sujeto_id = 'changed';
  expect(JSON.parse(intent.serializedBody)).toEqual({ sujeto_id: 'real-selected-id' });
  expect(Object.isFrozen(intent)).toBe(true);
  expect(Object.isFrozen(intent.headers)).toBe(true);
  expect(intent.headers['Idempotency-Key']).toBe(intent.key);
  expect(createCommandIntent('/v1/comandos/baja_de_sujeto', body).key).not.toBe(intent.key);
});
it('does not replay a mutation with an uncertain network result', async () => {
  const { session, mock } = fixture(); await session.login(login);
  mock.mockRejectedValueOnce(new TypeError('Network failure'));
  await expect(session.client.POST('/v1/comandos/baja_de_sujeto', { body: { sujeto_id: 'selected-id' } })).rejects.toThrow();
  expect(mock).toHaveBeenCalledTimes(3);
});
it('does not retry a consumable refresh after network uncertainty', async () => {
  const { session, mock, advance } = fixture(); await session.login(login); advance();
  mock.mockRejectedValueOnce(new TypeError('Network failure'));
  await expect(session.client.GET('/v1/auth/yo')).rejects.toThrow();
  expect(mock).toHaveBeenCalledTimes(3); expect(session.getSnapshot().status).toBe('anonymous');
});
it('blocks auth commands through the generic bearer client', async () => {
  const { session, mock } = fixture(); await session.login(login);
  await expect(session.client.POST('/v1/auth/refresh', { body: { refresh_token: 'must-not-send' } })).rejects.toThrow('dedicated transport');
  expect(mock).toHaveBeenCalledTimes(2);
});
it('aborts stalled login after the configured timeout', async () => {
  vi.useFakeTimers();
  try {
    const mock = vi.fn<typeof fetch>().mockImplementation((_input, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Timeout', 'AbortError')));
    }));
    const session = createSession({ baseUrl: 'https://api.example.com', fetch: mock, timeoutMs: 100 });
    const pending = session.login(login);
    await vi.advanceTimersByTimeAsync(100); await pending;
    expect(session.getSnapshot().status).toBe('anonymous'); expect(mock).toHaveBeenCalledTimes(1);
  } finally { vi.useRealTimers(); }
});
it('keeps signed storage outside the bearer client', async () => {
  const { session, mock } = fixture(); await session.login(login);
  await expect(session.client.GET('/v1/storage/{firma}', { params: { path: { firma: 'signed-value' } } })).rejects.toThrow('dedicated transport');
  expect(mock).toHaveBeenCalledTimes(2);
});
