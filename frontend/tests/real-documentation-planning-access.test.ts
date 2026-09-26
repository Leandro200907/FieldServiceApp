import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn() } } };
});

import { session } from '../src/api';
import { realDocumentationPlanningAccess, unwrap } from '../src/features/documentation-planning/realDocumentationPlanningAccess';

const getMock = vi.mocked(session.client.GET);
function okResponse(data: unknown) { return { data, error: undefined, response: new Response(null, { status: 200 }) }; }
function errorResponse(status: number, requestId = 'server-request-id') {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'no_encontrado', mensaje: 'no existe', detalles: null, request_id: requestId } }, response };
}

describe('unwrap', () => {
  it('returns data on success', async () => {
    await expect(unwrap(Promise.resolve(okResponse({ ok: true })))).resolves.toEqual({ ok: true });
  });
  it('turns HTTP failures into ApiFailure', async () => {
    await expect(unwrap(Promise.resolve(errorResponse(422)))).rejects.toMatchObject({ detail: { status: 422 } });
  });
});

describe('real documentary planning access', () => {
  it('maps the calendar query', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [] }));
    await realDocumentationPlanningAccess.readCalendar({ from: '2026-09-22', to: '2026-10-01', subjectKind: 'persona', q: 'marina', offset: 10, limit: 20 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/calendario_vigencias', {
      params: { query: { desde: '2026-09-22', hasta: '2026-10-01', tipo_sujeto: 'persona', q: 'marina', offset: 10, limit: 20 } },
    });
  });

  it('maps every radar backlog filter', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [] }));
    await realDocumentationPlanningAccess.readRadarBacklog({ from: '2026-09-22', to: '2026-10-01', clienteId: 'c', locacionId: 'l', tipoServicioId: 's', estado: ['con_alertas_documentales'], q: 'OC-1', offset: 0, limit: 50 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/radar_documental_backlog', {
      params: { query: { desde: '2026-09-22', hasta: '2026-10-01', cliente_id: 'c', locacion_id: 'l', tipo_servicio_id: 's', estado: ['con_alertas_documentales'], q: 'OC-1', offset: 0, limit: 50 } },
    });
  });

  it('uses the OC and legajo radar endpoints', async () => {
    getMock.mockResolvedValueOnce(okResponse({ estado_documental: 'sin_alertas_documentales' }));
    await realDocumentationPlanningAccess.readRadarOc({ ocId: '11111111-1111-1111-1111-111111111111' });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/radar_documental_oc', { params: { query: { oc_id: '11111111-1111-1111-1111-111111111111' } } });

    getMock.mockResolvedValueOnce(okResponse({ legajo: {} }));
    await realDocumentationPlanningAccess.readRadarLegajo({ ocId: '11111111-1111-1111-1111-111111111111', sujetoId: 'persona-1' });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/radar_documental_oc/{oc_id}/legajos/{sujeto_id}', { params: { path: { oc_id: '11111111-1111-1111-1111-111111111111', sujeto_id: 'persona-1' } } });
  });

  it('propagates a missing OC as ApiFailure', async () => {
    getMock.mockResolvedValueOnce(errorResponse(404));
    await expect(realDocumentationPlanningAccess.readRadarOc({ ocId: '11111111-1111-1111-1111-111111111111' })).rejects.toMatchObject({ detail: { status: 404 } });
  });
});


