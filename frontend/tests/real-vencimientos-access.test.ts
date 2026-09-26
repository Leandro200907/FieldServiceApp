import { describe, expect, it, vi } from 'vitest';

// Mismo patrón que tests/real-mi-legajo-access.test.ts.
vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn() } } };
});

import { session } from '../src/api';
import { realVencimientosAccess } from '../src/features/vencimientos/realVencimientosAccess';

const getMock = vi.mocked(session.client.GET);

function okResponse(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id') {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'prohibido', mensaje: 'sin rol suficiente', detalles: null, request_id: requestId } }, response };
}

describe('realVencimientosAccess', () => {
  it('readTableroVencimientos llama GET /v1/consultas/tablero_vencimientos con dias/offset/limit', async () => {
    getMock.mockResolvedValueOnce(okResponse({ hoy: '2026-09-22', hasta: '2026-10-22', items: [], total: 0, offset: 0, limit: 50 }));
    await realVencimientosAccess.readTableroVencimientos({ dias: 30, offset: 0, limit: 50 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/tablero_vencimientos', { params: { query: { dias: 30, offset: 0, limit: 50 } } });
  });

  it('propaga un 403 (rol sin acceso) como ApiFailure', async () => {
    getMock.mockResolvedValueOnce(errorResponse(403));
    await expect(realVencimientosAccess.readTableroVencimientos({})).rejects.toMatchObject({ detail: { status: 403 } });
  });
});
