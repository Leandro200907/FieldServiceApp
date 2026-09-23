import { ApiFailure, parseApiError, session } from '../../api';
import { createCommandIntent } from '../../api/idempotency';
import type { AsignacionesQuery, HistorialQuery, SujetoSearchQuery, SupervisionAccess, SupervisorSearchQuery } from './contracts';

// Adaptador real — mismo patrón que propuestas/realPropuestasAccess.ts para los dos
// comandos de escritura (usa `createCommandIntent` para una `Idempotency-Key` estable).
// `supervisor_usuario_id` siempre sale de `searchSupervisores` (rol=supervisor,
// alcance del tenant), nunca de un id libre elegido por el cliente.
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

export const realSupervisionAccess: SupervisionAccess = {
  async readAsignaciones(query: AsignacionesQuery) {
    return unwrap(session.client.GET('/v1/consultas/asignaciones_supervisor', {
      params: { query: { supervisor_usuario_id: query.supervisorUsuarioId, sujeto_id: query.sujetoId, solo_vigentes: query.soloVigentes, offset: query.offset, limit: query.limit } },
    }));
  },
  async readHistorial(query: HistorialQuery) {
    return unwrap(session.client.GET('/v1/consultas/historial_supervision', {
      params: { query: { sujeto_id: query.sujetoId, offset: query.offset, limit: query.limit } },
    }));
  },
  async searchSujetos(query: SujetoSearchQuery) {
    return unwrap(session.client.GET('/v1/consultas/sujetos', {
      params: { query: { q: query.q, offset: query.offset, limit: query.limit } },
    }));
  },
  async searchSupervisores(query: SupervisorSearchQuery) {
    return unwrap(session.client.GET('/v1/consultas/usuarios', {
      params: { query: { q: query.q, rol: 'supervisor', offset: query.offset, limit: query.limit } },
    }));
  },
  async asignarSupervisor(sujetoId: string, supervisorUsuarioId: string, desde?: string) {
    const intent = createCommandIntent('/v1/comandos/asignar_supervisor', { sujeto_id: sujetoId, supervisor_usuario_id: supervisorUsuarioId, desde: desde ?? null });
    return unwrap(session.client.POST('/v1/comandos/asignar_supervisor', {
      body: { sujeto_id: sujetoId, supervisor_usuario_id: supervisorUsuarioId, desde: desde ?? null }, headers: intent.headers,
    }));
  },
  async reasignarSupervisor(sujetoId: string, supervisorUsuarioId: string, desde?: string) {
    const intent = createCommandIntent('/v1/comandos/reasignar_supervisor', { sujeto_id: sujetoId, supervisor_usuario_id: supervisorUsuarioId, desde: desde ?? null });
    return unwrap(session.client.POST('/v1/comandos/reasignar_supervisor', {
      body: { sujeto_id: sujetoId, supervisor_usuario_id: supervisorUsuarioId, desde: desde ?? null }, headers: intent.headers,
    }));
  },
};
