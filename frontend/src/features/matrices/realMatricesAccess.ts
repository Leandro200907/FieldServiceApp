import { ApiFailure, parseApiError, session } from '../../api';
import type { MatricesAccess, MatricesQuery, MatrizVigenteQuery } from './contracts';

// Adaptador real — mismo patrón que el resto de features de solo lectura. No existe
// catálogo de nombres para cliente/locación/tipo de servicio (SEL-09/10/11 siguen
// abiertos) — se muestran los IDs crudos tal como los entrega el servidor.
async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

export const realMatricesAccess: MatricesAccess = {
  async readMatrices(query: MatricesQuery) {
    return unwrap(session.client.GET('/v1/consultas/matrices', {
      params: { query: { cliente_id: query.clienteId, solo_vigentes: query.soloVigentes, offset: query.offset, limit: query.limit } },
    }));
  },
  async readMatrizVigente(query: MatrizVigenteQuery) {
    return unwrap(session.client.GET('/v1/consultas/matriz_vigente', {
      params: { query: { cliente_id: query.clienteId, locacion_id: query.locacionId, tipo_servicio_id: query.tipoServicioId, fecha: query.fecha } },
    }));
  },
};
