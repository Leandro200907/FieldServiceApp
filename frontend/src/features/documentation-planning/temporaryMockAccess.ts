import type {
  BacklogProjection,
  BacklogQuery,
  CalendarInterval,
  CalendarProjection,
  CalendarQuery,
  DocumentationExplanation,
  DocumentationPlanningAccess,
  DocumentationScope,
  ExplanationQuery,
} from './contracts';
import { TEMPORARY_CONTRACT_SOURCE } from './contracts';

const scopeLabels: Record<DocumentationScope, string> = {
  responsible: 'Empresa completa dentro del alcance documental autorizado',
  supervisor: 'Equipo supervisado; no incluye sujetos fuera del universo asignado',
  technician: 'Mi persona y recursos propios autorizados',
};

const intervals: CalendarInterval[] = [
  { reference: 'CAL-EMP-01', subjectKind: 'empresa', subjectLabel: 'Empresa de servicios', requirementLabel: 'Registro de proveedor', from: '2026-09-01', to: '2026-10-18', state: 'verificada', applicability: { kind: 'matriz', label: 'Matriz publicada · Cliente Norte / Base Añelo' } },
  { reference: 'CAL-PER-01', subjectKind: 'persona', subjectLabel: 'Marina López', requirementLabel: 'Apto médico', from: '2026-09-08', to: '2026-09-27', state: 'proxima_a_vencer', applicability: { kind: 'oc', label: 'OC 45000218 · intervención prevista' } },
  { reference: 'CAL-PER-02', subjectKind: 'persona', subjectLabel: 'Diego Suárez', requirementLabel: 'Inducción de locación', from: '2026-08-18', to: '2026-09-17', state: 'vencida', applicability: { kind: 'matriz', label: 'Matriz publicada · Locación Sierra' } },
  { reference: 'CAL-VEH-01', subjectKind: 'vehiculo', subjectLabel: 'Unidad VX-23', requirementLabel: 'VTV', from: '2026-09-01', to: '2026-09-20', state: 'vencida', applicability: { kind: 'oc', label: 'OC 45000221 · requisito particular' } },
  { reference: 'CAL-EQP-01', subjectKind: 'equipo', subjectLabel: 'Detector multigás EQ-144', requirementLabel: 'Calibración informada', from: '2026-09-15', to: '2026-10-12', state: 'declarada', applicability: { kind: 'none', label: 'Sin matriz u OC que la establezca como obligación' } },
  { reference: 'CAL-EQP-02', subjectKind: 'equipo', subjectLabel: 'Medidor de presión EQ-087', requirementLabel: 'Certificado de calibración', from: '2026-09-21', to: '2026-10-25', state: 'sin_evidencia', applicability: { kind: 'matriz', label: 'Matriz publicada · Servicio de medición' } },
];

const backlog: BacklogProjection['rows'] = [
  { reference: 'BACK-01', ocLabel: 'OC 45000218', customerLabel: 'Cliente Norte', plannedFrom: '2026-09-24', plannedTo: '2026-09-30', state: 'sin_riesgos_detectados', firstRiskDay: null, reasons: ['La última evaluación no detectó cortes de vigencia dentro del período previsto.'], evaluationBasis: 'ultima_evaluacion', potentialCapacity: { personas: 12, vehiculos: 4, equipos: 9 } },
  { reference: 'BACK-02', ocLabel: 'OC 45000221', customerLabel: 'Operadora Sierra', plannedFrom: '2026-09-27', plannedTo: '2026-10-04', state: 'riesgo_documental', firstRiskDay: '2026-09-29', reasons: ['Dos aptos médicos vencen durante la ventana prevista.', 'Una VTV no cubre el último día planificado.'], evaluationBasis: 'ultima_evaluacion', potentialCapacity: { personas: 7, vehiculos: 2, equipos: 6 } },
  { reference: 'BACK-03', ocLabel: 'OC 45000224', customerLabel: 'Energía del Sur', plannedFrom: '2026-09-22', plannedTo: '2026-09-26', state: 'bloqueo_confirmado', firstRiskDay: '2026-09-22', reasons: ['La evaluación vigente confirmó evidencia obligatoria vencida para el contexto de la OC.'], evaluationBasis: 'ultima_evaluacion', potentialCapacity: { personas: 0, vehiculos: 0, equipos: 0 } },
  { reference: 'BACK-04', ocLabel: 'OC 45000231', customerLabel: 'Cliente Norte', plannedFrom: null, plannedTo: null, state: 'pendiente_planificacion', firstRiskDay: null, reasons: ['No hay fechas previstas suficientes para proyectar cobertura documental.'], evaluationBasis: 'pendiente_planificacion', potentialCapacity: { personas: 0, vehiculos: 0, equipos: 0 } },
  { reference: 'BACK-05', ocLabel: 'OC 45000236', customerLabel: 'Operadora Central', plannedFrom: '2026-10-05', plannedTo: '2026-10-10', state: 'sin_matriz', firstRiskDay: null, reasons: ['No existe una matriz publicada aplicable al contexto informado.'], evaluationBasis: 'ultima_evaluacion', potentialCapacity: { personas: 0, vehiculos: 0, equipos: 0 } },
  { reference: 'BACK-06', ocLabel: 'OC 45000240', customerLabel: 'Servicios Patagónicos', plannedFrom: '2026-10-12', plannedTo: '2026-10-18', state: 'requiere_revision', firstRiskDay: '2026-10-12', reasons: ['La evaluación contiene evidencia declarada pendiente de verificación.', 'El contexto de locación requiere confirmación.'], evaluationBasis: 'ultima_evaluacion', potentialCapacity: { personas: 3, vehiculos: 1, equipos: 2 } },
];

const explanations = new Map<string, DocumentationExplanation>([
  ...intervals.map(item => [item.reference, {
    source: TEMPORARY_CONTRACT_SOURCE,
    reference: item.reference,
    title: `${item.requirementLabel} · ${item.subjectLabel}`,
    summary: item.applicability.kind === 'none'
      ? 'Evidencia observada con fines informativos. No se presenta como requisito obligatorio.'
      : `Tramo proyectado entre ${item.from} y ${item.to}.`,
    reasons: [
      item.state === 'sin_evidencia' ? 'No se encontró evidencia verificada que cubra el intervalo.' : `Estado temporal propuesto: ${item.state.replaceAll('_', ' ')}.`,
      item.applicability.label,
    ],
    applicability: item.applicability,
    evaluationLabel: 'Detalle temporal de mock · pendiente de contrato backend',
  } as DocumentationExplanation] as const),
  ...backlog.map(row => [row.reference, {
    source: TEMPORARY_CONTRACT_SOURCE,
    reference: row.reference,
    title: `${row.ocLabel} · ${row.customerLabel}`,
    summary: row.evaluationBasis === 'ultima_evaluacion' ? 'Proyección basada en la última evaluación documental disponible.' : 'No se proyecta riesgo hasta recibir fechas de planificación.',
    reasons: row.reasons,
    applicability: row.state === 'sin_matriz' ? { kind: 'none', label: 'Sin matriz aplicable confirmada' } : { kind: 'oc', label: row.ocLabel },
    evaluationLabel: row.evaluationBasis === 'ultima_evaluacion' ? 'Utiliza la última evaluación' : 'Pendiente de planificación',
  } as DocumentationExplanation] as const),
]);

function allowedKinds(scope: DocumentationScope) {
  if (scope === 'responsible') return new Set(['empresa', 'persona', 'vehiculo', 'equipo']);
  return new Set(['persona', 'vehiculo', 'equipo']);
}

export const temporaryMockAccess: DocumentationPlanningAccess = {
  async readCalendar(query: CalendarQuery): Promise<CalendarProjection> {
    const allowed = allowedKinds(query.scope);
    return {
      source: TEMPORARY_CONTRACT_SOURCE,
      asOf: '2026-09-21',
      from: query.from,
      to: query.to,
      scopeLabel: scopeLabels[query.scope],
      intervals: intervals.filter(item => allowed.has(item.subjectKind) && (!query.subjectKind || item.subjectKind === query.subjectKind)),
    };
  },
  async readBacklogProjection(query: BacklogQuery): Promise<BacklogProjection> {
    return {
      source: TEMPORARY_CONTRACT_SOURCE,
      asOf: '2026-09-21',
      scopeLabel: scopeLabels[query.scope],
      warning: 'No garantiza disponibilidad ni asignación operativa',
      rows: query.scope === 'supervisor' ? backlog.slice(0, 6) : backlog,
    };
  },
  async readExplanation(query: ExplanationQuery): Promise<DocumentationExplanation> {
    const calendarItem = intervals.find(item => item.reference === query.reference);
    if (calendarItem && !allowedKinds(query.scope).has(calendarItem.subjectKind)) throw new Error('El detalle queda fuera del alcance visible para este rol.');
    if (query.scope === 'technician' && backlog.some(item => item.reference === query.reference)) throw new Error('La proyección del backlog no está disponible para este rol.');
    const detail = explanations.get(query.reference);
    if (!detail) throw new Error('El mock temporal no contiene el detalle solicitado.');
    return detail;
  },
};
