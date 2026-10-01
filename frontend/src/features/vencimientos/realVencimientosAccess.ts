import { ApiFailure, parseApiError, session } from '../../api';
import type { EspejoOperadoraQuery, HistorialOperadoraQuery, VencimientosAccess, VencimientosQuery } from './contracts';

// Adaptador real — mismo patrón que mi-legajo/realMiLegajoAccess.ts. `GET
// /v1/consultas/tablero_vencimientos` resuelve el alcance (empresa completa para
// responsable_legajos, universo propio para supervisor) desde `identidad` en el JWT; el
// cliente solo pasa `dias`/`offset`/`limit`.
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

export const realVencimientosAccess: VencimientosAccess = {
  async readTableroVencimientos(query: VencimientosQuery) {
    return unwrap(session.client.GET('/v1/consultas/tablero_vencimientos', {
      params: { query: { dias: query.dias, offset: query.offset, limit: query.limit } },
    }));
  },
  async readAlertasOperadora(query) {
    return unwrap(session.client.GET('/v1/consultas/alertas_actualizacion_operadora', {
      params: { query: { offset: query.offset, limit: query.limit } },
    }));
  },
  async readEspejoOperadora(query: EspejoOperadoraQuery) {
    return unwrap(session.client.GET('/v1/consultas/espejo_operadora', {
      params: {
        query: {
          offset: query.offset,
          limit: query.limit,
          operadora_id: query.operadora_id,
          requisito_definicion_id: query.requisito_definicion_id,
          tipo_sujeto: query.tipo_sujeto,
          q: query.q,
          estado_operadora: query.estado_operadora,
          movimiento_desde: query.movimiento_desde,
          movimiento_hasta: query.movimiento_hasta,
          mes: query.mes,
        },
      },
    }));
  },
  async readHistorialOperadora(query: HistorialOperadoraQuery) {
    return unwrap(session.client.GET('/v1/consultas/historial_operadora', {
      params: {
        query: {
          operadora_id: query.operadoraId,
          sujeto_id: query.sujetoId,
          requisito_definicion_id: query.requisitoDefinicionId,
        },
      },
    }));
  },
  async importarPlanilla(file) {
    return unwrap(session.client.POST('/v1/comandos/importar_planilla_operadoras', {
      params: {
        query: { hoja: 'Presentaciones' },
        header: { 'X-Nombre-Archivo': file.name, 'Idempotency-Key': crypto.randomUUID() },
      },
      body: file as unknown as string,
      bodySerializer: body => body as unknown as BodyInit,
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
    }));
  },
};


