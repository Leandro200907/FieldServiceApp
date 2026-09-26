import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn() } } };
});

import { session } from '../src/api';
import { realAuditoriaAccess } from '../src/features/auditoria/realAuditoriaAccess';

const getMock = vi.mocked(session.client.GET);

function okResponse(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id') {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'prohibido', mensaje: 'rol sin acceso', detalles: null, request_id: requestId } }, response };
}

describe('realAuditoriaAccess', () => {
  it('readLogAuditoria llama GET /v1/consultas/log_auditoria con tipo/desde/hasta/offset/limit', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [], total: 0, offset: 0, limit: 50 }));
    await realAuditoriaAccess.readLogAuditoria({ tipo: 'DocumentoConfirmado', desde: '2026-09-01T00:00:00Z', hasta: '2026-09-30T23:59:59Z', offset: 0, limit: 50 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/log_auditoria', { params: { query: { tipo: 'DocumentoConfirmado', desde: '2026-09-01T00:00:00Z', hasta: '2026-09-30T23:59:59Z', offset: 0, limit: 50 } } });
  });

  it('propaga un 403 (rol sin acceso) como ApiFailure', async () => {
    getMock.mockResolvedValueOnce(errorResponse(403));
    await expect(realAuditoriaAccess.readLogAuditoria({})).rejects.toMatchObject({ detail: { status: 403 } });
  });
});
