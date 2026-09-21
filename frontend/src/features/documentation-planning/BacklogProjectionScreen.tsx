import { useState } from 'react';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import type { DocumentationExplanation, ProjectionState } from './contracts';
import { temporaryMockAccess } from './temporaryMockAccess';
import { documentationScopeFor } from './scope';
import { usePrototypeRead } from './usePrototypeRead';
import './planning.css';

const stateLabels: Record<ProjectionState, string> = {
  sin_riesgos_detectados: 'Sin riesgos detectados', riesgo_documental: 'Riesgo documental', bloqueo_confirmado: 'Bloqueo confirmado', pendiente_planificacion: 'Pendiente de planificación', sin_matriz: 'Sin matriz', requiere_revision: 'Requiere revisión',
};
function displayDate(value: string | null) { return value ? new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: 'short' }).format(new Date(`${value}T12:00:00`)) : 'Sin fecha'; }
function ExplanationPanel({ detail }: { detail: DocumentationExplanation }) {
  return <section className="panel backlog-detail" aria-live="polite"><div><p className="eyebrow">Explicación seleccionada</p><h3>{detail.title}</h3><p>{detail.summary}</p></div><div><strong>{detail.evaluationLabel}</strong><ul>{detail.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></div></section>;
}
export function BacklogProjectionScreen({ roles }: { roles: readonly string[] }) {
  const resolved = documentationScopeFor(roles);
  const scope = resolved === 'technician' ? 'supervisor' : resolved;
  const [selected, setSelected] = useState('BACK-02');
  const projection = usePrototypeRead(() => temporaryMockAccess.readBacklogProjection({ scope, from: '2026-09-21', to: '2026-10-31' }), [scope]);
  const detail = usePrototypeRead(() => temporaryMockAccess.readExplanation({ scope, reference: selected }), [scope, selected]);
  return <>
    <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Proyección no integrada</strong><p>Una fila por OC con datos de ejemplo. No registra planificación ni confirma recursos.</p></div></div>
    <div className="availability-warning" role="note"><strong>No garantiza disponibilidad ni asignación operativa</strong><span>Los conteos representan capacidad documental potencial según el mock, nunca disponibilidad.</span></div>
    <section className="panel projection-summary"><div><p className="eyebrow">Alcance visible</p><strong>{projection.data?.scopeLabel || 'Resolviendo alcance del prototipo…'}</strong></div><div><p className="eyebrow">Ventana proyectada</p><strong>21 sep — 31 oct 2026</strong></div></section>
    {projection.loading ? <LoadingState /> : projection.error ? <ErrorState message={projection.error.message} /> : <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>OC</th><th>Fechas previstas</th><th>Estado documental</th><th>Primer día de riesgo</th><th>Base de la proyección</th><th>Capacidad documental potencial</th><th>Motivos</th></tr></thead><tbody>{projection.data?.rows.map(row => <tr key={row.reference} className={selected === row.reference ? 'selected-row' : ''}><td><strong>{row.ocLabel}</strong><small>{row.customerLabel}</small></td><td>{displayDate(row.plannedFrom)} — {displayDate(row.plannedTo)}</td><td><span className={`projection-status projection-${row.state}`}>{stateLabels[row.state]}</span></td><td>{displayDate(row.firstRiskDay)}</td><td>{row.evaluationBasis === 'ultima_evaluacion' ? 'Última evaluación' : 'Pendiente de planificación'}</td><td><span>{row.potentialCapacity.personas} personas</span><span>{row.potentialCapacity.vehiculos} vehículos</span><span>{row.potentialCapacity.equipos} equipos</span></td><td><button className="text-button" onClick={() => setSelected(row.reference)}>Ver motivos</button></td></tr>)}</tbody></table></div>}
    {detail.loading ? <LoadingState /> : detail.error ? <ErrorState message={detail.error.message} /> : detail.data && <ExplanationPanel detail={detail.data} />}
    <section className="module-boundary"><strong>Solo proyección documental del Módulo 1</strong><span>Sin disponibilidad</span><span>Sin asignar recursos</span><span>Sin modificar fechas ni crear OT</span><span>Sin ejecución, tiempos reales, firma ni certificados</span></section>
  </>;
}
