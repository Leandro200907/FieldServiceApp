import { describe, expect, it, vi } from 'vitest';

// Mismo patrón que tests/real-documentation-planning-access.test.ts (F-10): se mockea el
// módulo `../src/api` para reemplazar sólo `session` (con `client.GET` espiable) y dejar
// `ApiFailure`/`parseApiError` reales.
vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn() } } };
});

import { session } from '../src/api';
import { realMiLegajoAccess } from '../src/features/mi-legajo/realMiLegajoAccess';

const getMock = vi.mocked(session.client.GET);

function okResponse(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id') {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'prohibido', mensaje: 'sin legajo propio', detalles: null, request_id: requestId } }, response };
}

describe('realMiLegajoAccess', () => {
  it('readMiLegajo llama GET /v1/consultas/mi_legajo sin ningún parámetro (el servidor resuelve el sujeto propio desde el JWT)', async () => {
    getMock.mockResolvedValueOnce(okResponse({ hoy: '2026-09-22', persona: {}, recursos_bajo_custodia: [], resumen: { vencidos: 0, vigentes_hoy: 0 } }));
    await realMiLegajoAccess.readMiLegajo();
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/mi_legajo');
  });

  it('propaga un 403 (sin sujeto_id propio — configuracion/responsable_legajos sin legajo) como ApiFailure', async () => {
    getMock.mockResolvedValueOnce(errorResponse(403));
    await expect(realMiLegajoAccess.readMiLegajo()).rejects.toMatchObject({ detail: { status: 403 } });
  });
});
