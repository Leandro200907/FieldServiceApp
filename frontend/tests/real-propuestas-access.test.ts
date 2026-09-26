import { describe, expect, it, vi } from 'vitest';

// Mismo patrón que tests/real-legajos-access.test.ts, extendido para cubrir POST.
vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn(), POST: vi.fn() } } };
});

import { session } from '../src/api';
import { realPropuestasAccess } from '../src/features/propuestas/realPropuestasAccess';

const getMock = vi.mocked(session.client.GET);
const postMock = vi.mocked(session.client.POST);

// `session.client.POST` is typed as a union across every command path (each with its own
// body/response shape); a loosely-typed fixture can't satisfy that union structurally, so
// these helpers return `any` — same values, just not narrowed to one specific operation.
function okResponse(data: unknown): any {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id'): any {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'no_encontrado', mensaje: 'documento inexistente', detalles: null, request_id: requestId } }, response };
}

describe('realPropuestasAccess', () => {
  it('readPropuestasPendientes llama GET /v1/consultas/propuestas_pendientes con offset/limit', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [], total: 0, offset: 0, limit: 50 }));
    await realPropuestasAccess.readPropuestasPendientes({ offset: 0, limit: 50 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/propuestas_pendientes', { params: { query: { offset: 0, limit: 50 } } });
  });

  it('confirmarDocumento llama POST /v1/comandos/confirmar_documento con Idempotency-Key', async () => {
    postMock.mockResolvedValueOnce(okResponse({ documento_id: 'doc-1', excepciones_regularizadas: [], eventos: ['documento_confirmado'] }));
    await realPropuestasAccess.confirmarDocumento('doc-1');
    expect(postMock).toHaveBeenCalledTimes(1);
    const [path, options] = postMock.mock.calls[0];
    expect(path).toBe('/v1/comandos/confirmar_documento');
    expect(options?.body).toEqual({ documento_id: 'doc-1' });
    expect(options?.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) });
  });

  it('rechazarPropuesta llama POST /v1/comandos/rechazar_propuesta con motivo e Idempotency-Key', async () => {
    postMock.mockResolvedValueOnce(okResponse({ documento_id: 'doc-2', restaurado_documento_id: null, eventos: ['propuesta_rechazada'] }));
    await realPropuestasAccess.rechazarPropuesta('doc-2', 'sin evidencia adjunta');
    const [path, options] = postMock.mock.calls[0];
    expect(path).toBe('/v1/comandos/rechazar_propuesta');
    expect(options?.body).toEqual({ documento_id: 'doc-2', motivo: 'sin evidencia adjunta' });
    expect(options?.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) });
  });

  it('propaga un 404 (documento inexistente) como ApiFailure', async () => {
    postMock.mockResolvedValueOnce(errorResponse(404));
    await expect(realPropuestasAccess.confirmarDocumento('doc-inexistente')).rejects.toMatchObject({ detail: { status: 404 } });
  });
});
