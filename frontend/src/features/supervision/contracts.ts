import type { components } from '../../api/generated/modulo1';
import type { SujetoItem, SujetosResponse } from '../legajos/contracts';

// Tipos reales del backend — no se redeclaran a mano. `SujetoItem`/`SujetosResponse` se
// reusan de legajos/contracts.ts: es exactamente el mismo `GET /v1/consultas/sujetos`.
export type { SujetoItem, SujetosResponse };
export type UsuarioItem = components['schemas']['UsuarioItem'];
export type UsuariosResponse = components['schemas']['UsuariosResponse'];
export type AsignacionSupervisorItem = components['schemas']['AsignacionSupervisorItem'];
export type AsignacionesSupervisorResponse = components['schemas']['AsignacionesSupervisorResponse'];
export type AsignacionSupervisionHistorial = components['schemas']['AsignacionSupervisionHistorial'];
export type HistorialSupervisionResponse = components['schemas']['HistorialSupervisionResponse'];
export type AsignarSupervisorResponse = components['schemas']['AsignarSupervisorResponse'];
export type ReasignarSupervisorResponse = components['schemas']['ReasignarSupervisorResponse'];

export interface AsignacionesQuery {
  supervisorUsuarioId?: string;
  sujetoId?: string;
  soloVigentes?: boolean;
  offset?: number;
  limit?: number;
}

export interface HistorialQuery {
  sujetoId: string;
  offset?: number;
  limit?: number;
}

export interface SujetoSearchQuery {
  q?: string;
  offset?: number;
  limit?: number;
}

export interface SupervisorSearchQuery {
  q?: string;
  offset?: number;
  limit?: number;
}

export interface SupervisionAccess {
  readAsignaciones(query: AsignacionesQuery): Promise<AsignacionesSupervisorResponse>;
  readHistorial(query: HistorialQuery): Promise<HistorialSupervisionResponse>;
  searchSujetos(query: SujetoSearchQuery): Promise<SujetosResponse>;
  searchSupervisores(query: SupervisorSearchQuery): Promise<UsuariosResponse>;
  asignarSupervisor(sujetoId: string, supervisorUsuarioId: string, desde?: string): Promise<AsignarSupervisorResponse>;
  reasignarSupervisor(sujetoId: string, supervisorUsuarioId: string, desde?: string): Promise<ReasignarSupervisorResponse>;
}
