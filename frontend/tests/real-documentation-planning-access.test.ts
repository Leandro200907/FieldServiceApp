import { describe, expect, it, vi } from 'vitest';

// F-10 (auditoría externa 2026-09-22): hasta acá, la suite sólo ejercitaba
// `temporaryMockAccess` — ningún test tocaba el adaptador real ni `unwrap`, así que un
// path de OpenAPI mal escrito o un mapeo de query roto no los pescaba vitest (sólo el
// typecheck, y sólo si el error rompía la firma de `session.client`). Se mockea el
// módulo `../src/api` para reemplazar sólo `session` (con `client.GET` espiable) y dejar
// `ApiFailure`/`parseApiError` reales — así `unwrap` corre con su lógica de verdad.
vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn() } } };
});

import { session } from '../src/api';
import { realDocumentationPlanningAccess, unwrap } from '../src/features/documentation-planning/realDocumentationPlanningAccess';

const getMock = vi.mocked(session.client.GET);

function okResponse(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id') {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'no_encontrado', mensaje: 'no existe', detalles: null, request_id: requestId } }, response };
}

describe('unwrap', () => {
  it('devuelve `data` cuando la respuesta es 200 y openapi-fetch no reporta error', async () => {
    const data = { hoy: '2026-09-22' };
    await expect(unwrap(Promise.resolve(okResponse(data)))).resolves.toBe(data);
  });

  it('lanza ApiFailure cuando openapi-fetch reporta error (nunca lanza por su cuenta)', async () => {
    await expect(unwrap(Promise.resolve(errorResponse(422)))).rejects.toMatchObject({ detail: { status: 422 } });
  });

  it('lanza ApiFailure incluso con response.ok pero `data` undefined (contrato roto: 200 sin body)', async () => {
    await expect(unwrap(Promise.resolve({ data: undefined, error: undefined, response: new Response(null, { status: 200 }) })))
      .rejects.toThrow();
  });
});

describe('realDocumentationPlanningAccess — pega contra el path y los query params reales', () => {
  it('readCalendar llama GET /v1/consultas/calendario_vigencias con desde/hasta/tipo_sujeto/q/offset/limit', async () => {
    getMock.mockResolvedValueOnce(okResponse({ hoy: '2026-09-22', desde: '2026-09-22', hasta: '2026-10-01', items: [], total: 0, offset: 0, limit: 50, advertencia: 'x' }));
    await realDocumentationPlanningAccess.readCalendar({ from: '2026-09-22', to: '2026-10-01', subjectKind: 'persona', q: 'marina', offset: 10, limit: 20 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/calendario_vigencias', {
      params: { query: { desde: '2026-09-22', hasta: '2026-10-01', tipo_sujeto: 'persona', q: 'marina', offset: 10, limit: 20 } },
    });
  });

  it('readBacklogProjection llama GET /v1/consultas/proyeccion_documental_backlog con estado_oc/estado/horizonte_dias/offset/limit', async () => {
    getMock.mockResolvedValueOnce(okResponse({ hoy: '2026-09-22', horizonte_dias: 30, items: [], total: 0, offset: 0, limit: 50, advertencia: 'x' }));
    await realDocumentationPlanningAccess.readBacklogProjection({ estadoOc: 'activo', estado: ['riesgo_documental'], horizonteDias: 30, offset: 0, limit: 50 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/proyeccion_documental_backlog', {
      params: { query: { estado_oc: 'activo', estado: ['riesgo_documental'], horizonte_dias: 30, offset: 0, limit: 50 } },
    });
  });

  it('readProjectionDetail llama GET /v1/consultas/proyeccion_documental con commitment_id/desde/hasta/detalle', async () => {
    getMock.mockResolvedValueOnce(okResponse({ commitment_id: 'OC-1', referencia: 'oc:OC-1' }));
    await realDocumentationPlanningAccess.readProjectionDetail({ commitmentId: 'OC-1', desde: '2026-09-22', hasta: '2026-10-01', detalle: 'diario' });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/proyeccion_documental', {
      params: { query: { commitment_id: 'OC-1', desde: '2026-09-22', hasta: '2026-10-01', detalle: 'diario' } },
    });
  });

  it('propaga un 404 real de `readProjectionDetail` como ApiFailure, no como excepción genérica', async () => {
    getMock.mockResolvedValueOnce(errorResponse(404));
    await expect(realDocumentationPlanningAccess.readProjectionDetail({ commitmentId: 'OC-inexistente' }))
      .rejects.toMatchObject({ detail: { status: 404 } });
  });
});
