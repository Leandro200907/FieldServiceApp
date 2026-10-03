import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { GET: vi.fn() } } };
});

import { session } from '../src/api';
import { realMatricesAccess } from '../src/features/matrices/realMatricesAccess';

const getMock = vi.mocked(session.client.GET);

function okResponse(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}
function errorResponse(status: number, requestId = 'server-request-id') {
  const response = new Response(null, { status, headers: { 'X-Request-ID': requestId } });
  return { data: undefined, error: { error: { codigo: 'no_encontrado', mensaje: 'sin matriz vigente', detalles: null, request_id: requestId } }, response };
}

describe('realMatricesAccess', () => {
  it('readMatrices llama GET /v1/consultas/matrices con cliente_id/solo_vigentes/offset/limit', async () => {
    getMock.mockResolvedValueOnce(okResponse({ items: [], total: 0, offset: 0, limit: 50 }));
    await realMatricesAccess.readMatrices({ clienteId: 'cliente-norte', soloVigentes: true, offset: 0, limit: 50 });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/matrices', { params: { query: { cliente_id: 'cliente-norte', solo_vigentes: true, offset: 0, limit: 50 } } });
  });

  it('readMatrizVigente llama GET /v1/consultas/matriz_vigente con cliente_id/locacion_id/tipo_servicio_id/fecha', async () => {
    getMock.mockResolvedValueOnce(okResponse({ matriz_version_id: 'matriz-1', cliente_id: 'c', locacion_id: 'l', tipo_servicio_id: 't', version: 1, vigente_desde: '2026-01-01', vigente_hasta: null, fuente: null, archivo_de_respaldo: null, autor: null, creado_en: '2026-01-01T00:00:00Z', fecha_consultada: '2026-09-21', lineas: [] }));
    await realMatricesAccess.readMatrizVigente({ clienteId: 'cliente-norte', locacionId: 'locacion-norte-01', tipoServicioId: 'servicio-mantenimiento', fecha: '2026-09-21' });
    expect(getMock).toHaveBeenCalledWith('/v1/consultas/matriz_vigente', { params: { query: { cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-01', tipo_servicio_id: 'servicio-mantenimiento', fecha: '2026-09-21' } } });
  });

  it('propaga un 404 (sin matriz vigente en esa fecha) como ApiFailure', async () => {
    getMock.mockResolvedValueOnce(errorResponse(404));
    await expect(realMatricesAccess.readMatrizVigente({ clienteId: 'x', locacionId: 'y', tipoServicioId: 'z' })).rejects.toMatchObject({ detail: { status: 404 } });
  });
});
