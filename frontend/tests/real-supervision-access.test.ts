import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn(), POST: vi.fn() } } };
});

import { session } from '../src/api';
import { realSupervisionAccess } from '../src/features/supervision/realSupervisionAccess';

const getMock = vi.mocked(session.client.GET);
const postMock = vi.mocked(session.client.POST);

function okResponse(data: unknown): any {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id'): any {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'conflicto', mensaje: 'ya tiene supervisor vigente', detalles: null, request_id: requestId } }, response };
}

describe('realSupervisionAccess', () => {
  it('readAsignaciones llama GET /v1/consultas/asignaciones_supervisor con los filtros', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [], total: 0, offset: 0, limit: 50 }));
    await realSupervisionAccess.readAsignaciones({ soloVigentes: true, offset: 0, limit: 50 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/asignaciones_supervisor', { params: { query: { supervisor_usuario_id: undefined, sujeto_id: undefined, solo_vigentes: true, offset: 0, limit: 50 } } });
  });

  it('readHistorial llama GET /v1/consultas/historial_supervision con sujeto_id', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [], total: 0, offset: 0, limit: 50 }));
    await realSupervisionAccess.readHistorial({ sujetoId: 'persona-marina' });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/historial_supervision', { params: { query: { sujeto_id: 'persona-marina', offset: undefined, limit: undefined } } });
  });

  it('searchSupervisores llama GET /v1/consultas/usuarios con rol=supervisor', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [], total: 0, offset: 0, limit: 50 }));
    await realSupervisionAccess.searchSupervisores({ q: 'ana' });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/usuarios', { params: { query: { q: 'ana', rol: 'supervisor', offset: undefined, limit: undefined } } });
  });

  it('asignarSupervisor llama POST /v1/comandos/asignar_supervisor con Idempotency-Key', async () => {
    postMock.mockResolvedValueOnce(okResponse({ asignacion_id: 'asig-1', sujeto_id: 'persona-diego', desde: '2026-09-23', eventos: ['SupervisorAsignado'] }));
    await realSupervisionAccess.asignarSupervisor('persona-diego', 'usr-supervisor-01');
    const [path, options] = postMock.mock.calls[0];
    expect(path).toBe('/v1/comandos/asignar_supervisor');
    expect(options?.body).toEqual({ sujeto_id: 'persona-diego', supervisor_usuario_id: 'usr-supervisor-01', desde: null });
    expect(options?.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) });
  });

  it('reasignarSupervisor llama POST /v1/comandos/reasignar_supervisor con Idempotency-Key', async () => {
    postMock.mockResolvedValueOnce(okResponse({ asignacion_id: 'asig-2', asignacion_cerrada_id: 'asig-1', sujeto_id: 'persona-marina', desde: '2026-09-23', hasta_anterior: '2026-09-22', eventos: ['SupervisorReasignado'] }));
    await realSupervisionAccess.reasignarSupervisor('persona-marina', 'usr-supervisor-02', '2026-09-23');
    const [path, options] = postMock.mock.calls[0];
    expect(path).toBe('/v1/comandos/reasignar_supervisor');
    expect(options?.body).toEqual({ sujeto_id: 'persona-marina', supervisor_usuario_id: 'usr-supervisor-02', desde: '2026-09-23' });
    expect(options?.headers).toMatchObject({ 'Idempotency-Key': expect.any(String) });
  });

  it('propaga un 409 (ya tiene supervisor vigente) como ApiFailure', async () => {
    postMock.mockResolvedValueOnce(errorResponse(409));
    await expect(realSupervisionAccess.asignarSupervisor('persona-marina', 'usr-supervisor-01')).rejects.toMatchObject({ detail: { status: 409 } });
  });
});
