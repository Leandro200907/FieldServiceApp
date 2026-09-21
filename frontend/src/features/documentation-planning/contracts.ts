export const TEMPORARY_CONTRACT_SOURCE = 'temporary-contract-mock' as const;

export type DocumentationScope = 'responsible' | 'supervisor' | 'technician';
export type SubjectKind = 'empresa' | 'persona' | 'vehiculo' | 'equipo';
export type EvidenceIntervalState = 'verificada' | 'proxima_a_vencer' | 'vencida' | 'declarada' | 'sin_evidencia';
export type ProjectionState =
  | 'sin_riesgos_detectados'
  | 'riesgo_documental'
  | 'bloqueo_confirmado'
  | 'pendiente_planificacion'
  | 'sin_matriz'
  | 'requiere_revision';

export interface ApplicabilityContext {
  kind: 'matriz' | 'oc' | 'none';
  label: string;
}

export interface CalendarInterval {
  reference: string;
  subjectKind: SubjectKind;
  subjectLabel: string;
  requirementLabel: string;
  from: string;
  to: string;
  state: EvidenceIntervalState;
  applicability: ApplicabilityContext;
}

export interface CalendarProjection {
  source: typeof TEMPORARY_CONTRACT_SOURCE;
  asOf: string;
  from: string;
  to: string;
  scopeLabel: string;
  intervals: CalendarInterval[];
}

export interface PotentialCapacity {
  personas: number;
  vehiculos: number;
  equipos: number;
}

export interface BacklogProjectionRow {
  reference: string;
  ocLabel: string;
  customerLabel: string;
  plannedFrom: string | null;
  plannedTo: string | null;
  state: ProjectionState;
  firstRiskDay: string | null;
  reasons: string[];
  evaluationBasis: 'ultima_evaluacion' | 'pendiente_planificacion';
  potentialCapacity: PotentialCapacity;
}

export interface BacklogProjection {
  source: typeof TEMPORARY_CONTRACT_SOURCE;
  asOf: string;
  scopeLabel: string;
  warning: 'No garantiza disponibilidad ni asignación operativa';
  rows: BacklogProjectionRow[];
}

export interface DocumentationExplanation {
  source: typeof TEMPORARY_CONTRACT_SOURCE;
  reference: string;
  title: string;
  summary: string;
  reasons: string[];
  applicability: ApplicabilityContext;
  evaluationLabel: string;
}

export interface CalendarQuery {
  scope: DocumentationScope;
  from: string;
  to: string;
  subjectKind?: SubjectKind;
}

export interface BacklogQuery {
  scope: Exclude<DocumentationScope, 'technician'>;
  from: string;
  to: string;
}

export interface ExplanationQuery {
  scope: DocumentationScope;
  reference: string;
}

export interface DocumentationPlanningAccess {
  readCalendar(query: CalendarQuery): Promise<CalendarProjection>;
  readBacklogProjection(query: BacklogQuery): Promise<BacklogProjection>;
  readExplanation(query: ExplanationQuery): Promise<DocumentationExplanation>;
}
