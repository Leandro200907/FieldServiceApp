import type { components } from '../../api/generated/modulo1';

// Tipos reales del backend. El radar es informativo: cruza la fecha prevista de la OC,
// la matriz aplicable y la documentación registrada, sin asignar ni sugerir recursos.
// No se redeclaran a mano: cualquier divergencia con el contrato real tiene que aparecer
// acá como un error de TypeScript al regenerar `src/api/generated/modulo1.d.ts`, nunca
// como un campo que "se parece" pero no es el mismo.
export type ItemCalendario = components['schemas']['ItemCalendario'];
export type CalendarioVigenciasResponse = components['schemas']['CalendarioVigenciasResponse'];
export type ItemRadar = components['schemas']['ItemRadar'];
export type RadarBacklogResponse = components['schemas']['RadarBacklogResponse'];
export type DetalleOcRadarResponse = components['schemas']['DetalleOcRadarResponse'];
export type DetalleLegajoRadarResponse = components['schemas']['DetalleLegajoRadarResponse'];
export type ConteoTipo = components['schemas']['ConteoTipo'];

export type SubjectKind = 'empresa' | 'persona' | 'vehiculo' | 'equipo';
// Rol resuelto del lado del cliente SOLO para etiquetas y navegación — nunca se envía al
// backend. El alcance real (qué sujetos/OC ve cada quien) lo resuelve el servidor con
// `alcance_de_sujetos` a partir del JWT; estos tres endpoints no reciben ningún parámetro
// de alcance ni de rol.
export type DocumentationScope = 'responsible' | 'supervisor' | 'technician';

export type RadarState = ItemRadar['estado_documental'];

// `calendario_vigencias` expone `estado_visual_calendario` calculado en el backend.
export type VisualCalendarState = ItemCalendario['estado_visual_calendario'];

export function deriveVisualState(
  item: Pick<ItemCalendario, 'estado_visual_calendario'>,
): VisualCalendarState {
  return item.estado_visual_calendario;
}

export interface CalendarQuery {
  from?: string;
  to?: string;
  subjectKind?: SubjectKind;
  q?: string;
  offset?: number;
  limit?: number;
}

export interface BacklogQuery {
  from?: string;
  to?: string;
  clienteId?: string;
  locacionId?: string;
  tipoServicioId?: string;
  estado?: RadarState[];
  q?: string;
  offset?: number;
  limit?: number;
}

export interface RadarOcQuery { ocId: string; offset?: number; limit?: number }
export interface RadarLegajoQuery { ocId: string; sujetoId: string }

export interface DocumentationPlanningAccess {
  readCalendar(query: CalendarQuery): Promise<CalendarioVigenciasResponse>;
  readRadarBacklog(query: BacklogQuery): Promise<RadarBacklogResponse>;
  readRadarOc(query: RadarOcQuery): Promise<DetalleOcRadarResponse>;
  readRadarLegajo(query: RadarLegajoQuery): Promise<DetalleLegajoRadarResponse>;
}

