import { describe, expect, it, vi } from 'vitest';

// Mismo patrón que tests/real-vencimientos-access.test.ts.
vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn() } } };
});

import { session } from '../src/api';
import { realLegajosAccess } from '../src/features/legajos/realLegajosAccess';

const getMock = vi.mocked(session.client.GET);

function okResponse(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id') {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'prohibido', mensaje: 'sujeto fuera de alcance', detalles: null, request_id: requestId } }, response };
}

describe('realLegajosAccess', () => {
  it('searchSujetos llama GET /v1/consultas/sujetos con q/tipo_sujeto/offset/limit', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [], total: 0, offset: 0, limit: 20 }));
    await realLegajosAccess.searchSujetos({ q: 'marina', tipoSujeto: 'persona', limit: 20 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/sujetos', { params: { query: { q: 'marina', tipo_sujeto: 'persona', offset: undefined, limit: 20 } } });
  });

  it('readLegajo llama GET /v1/consultas/legajo con sujeto_id', async () => {
    getMock.mockResolvedValueOnce(okResponse({ hoy: '2026-09-22', legajo: {}, documentos: [], acreditaciones: [], inducciones: [], resumen: { total: 0, vigentes_hoy: 0, vencidos: 0 } }));
    await realLegajosAccess.readLegajo('persona-marina');
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/legajo', { params: { query: { sujeto_id: 'persona-marina' } } });
  });

  it('propaga un 403 (sujeto fuera de alcance) como ApiFailure', async () => {
    getMock.mockResolvedValueOnce(errorResponse(403));
    await expect(realLegajosAccess.readLegajo('persona-ajena')).rejects.toMatchObject({ detail: { status: 403 } });
  });
});
