import type { components } from '../../api/generated/modulo1';

export type EventoAuditoria = components['schemas']['EventoAuditoria'];
export type LogAuditoriaResponse = components['schemas']['LogAuditoriaResponse'];

export interface AuditoriaQuery {
  tipo?: string;
  desde?: string;
  hasta?: string;
  offset?: number;
  limit?: number;
}

export interface AuditoriaAccess {
  readLogAuditoria(query: AuditoriaQuery): Promise<LogAuditoriaResponse>;
}
