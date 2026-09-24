import type { components } from '../../api/generated/modulo1';

// Tipos reales del backend (docs/PROYECCION_DOCUMENTAL.md + HANDOFF_PROYECCION_ASTRA.md).
// No se redeclaran a mano: cualquier divergencia con el contrato real tiene que aparecer
// acá como un error de TypeScript al regenerar `src/api/generated/modulo1.d.ts`, nunca
// como un campo que "se parece" pero no es el mismo.
export type ItemCalendario = components['schemas']['ItemCalendario'];
export type CalendarioVigenciasResponse = components['schemas']['CalendarioVigenciasResponse'];
export type ItemBacklog = components['schemas']['ItemBacklog'];
export type ProyeccionDocumentalBacklogResponse = components['schemas']['ProyeccionDocumentalBacklogResponse'];
export type ProyeccionDocumentalResponse = components['schemas']['ProyeccionDocumentalResponse'];
export type IntervaloProyeccion = components['schemas']['IntervaloProyeccion'];
export type CausaProyeccion = components['schemas']['CausaProyeccion'];
export type SujetosOrigen = components['schemas']['SujetosOrigen'];
export type MatrizInfo = components['schemas']['MatrizInfo'];
export type OcInfo = components['schemas']['OcInfo'];

export type SubjectKind = 'empresa' | 'persona' | 'vehiculo' | 'equipo';
// Rol resuelto del lado del cliente SOLO para etiquetas y navegación — nunca se envía al
// backend. El alcance real (qué sujetos/OC ve cada quien) lo resuelve el servidor con
// `alcance_de_sujetos` a partir del JWT; estos tres endpoints no reciben ningún parámetro
// de alcance ni de rol.
export type DocumentationScope = 'responsible' | 'supervisor' | 'technician';

// Los 6 estados resumen (proyección puntual y cada fila del backlog) — vocabulario cerrado
// de docs/PROYECCION_DOCUMENTAL.md §6. `estado` de `ProyeccionDocumentalResponse`/
// `ItemBacklog` ya está tipado con este mismo literal por el generador; se re-exporta acá
// solo para no repetir la unión en cada componente.
export type ProjectionState = ProyeccionDocumentalResponse['estado'];
// Los 3 estados de INTERVALO (subconjunto de los 6 — nunca incluye `riesgo_documental`,
// `sin_matriz` ni `pendiente_de_planificacion`, que son exclusivamente de resumen).
export type IntervalState = IntervaloProyeccion['estado'];

// `calendario_vigencias` NO cruza contra matriz/OC (confirmado en
// docs/PROYECCION_DOCUMENTAL.md §2.1) — no tiene un campo `estado` de evidencia. Los 3
// estados visuales de abajo son una presentación INEQUÍVOCA de campos ya devueltos por
// `ItemCalendario`, sin ningún umbral inventado (fórmulas fijadas en
// docs/PROYECCION_DOCUMENTAL.md §3.1). Deliberadamente NO incluye `proxima_a_vencer`
// (necesita `plazo_aviso_dias`, que este endpoint no entrega hoy) ni `sin_evidencia` (la
// ausencia de un ítem ES la señal; nunca es un valor de estado).
export type VisualCalendarState = 'declarada' | 'verificada' | 'vencida';

export function deriveVisualState(item: Pick<ItemCalendario, 'estado_confirmacion' | 'dias_para_vencer'>): VisualCalendarState {
  if (item.estado_confirmacion === 'declarado') return 'declarada';
  if (item.dias_para_vencer < 0) return 'vencida';
  return 'verificada';
}

export interface CalendarQuery {
  from: string;
  to: string;
  subjectKind?: SubjectKind;
  q?: string;
  offset?: number;
  limit?: number;
}

export interface BacklogQuery {
  estadoOc?: 'activo' | 'cancelado';
  estado?: ProjectionState[];
  horizonteDias?: number;
  offset?: number;
  limit?: number;
}

export interface ProjectionDetailQuery {
  commitmentId: string;
  desde?: string;
  hasta?: string;
  detalle?: 'resumen' | 'diario';
}

export interface DocumentationPlanningAccess {
  readCalendar(query: CalendarQuery): Promise<CalendarioVigenciasResponse>;
  readBacklogProjection(query: BacklogQuery): Promise<ProyeccionDocumentalBacklogResponse>;
  readProjectionDetail(query: ProjectionDetailQuery): Promise<ProyeccionDocumentalResponse>;
}
