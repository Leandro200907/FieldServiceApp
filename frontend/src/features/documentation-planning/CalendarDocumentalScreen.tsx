import { useState } from 'react';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import type { CalendarInterval, DocumentationExplanation, EvidenceIntervalState, SubjectKind } from './contracts';
import { temporaryMockAccess } from './temporaryMockAccess';
import { documentationScopeFor } from './scope';
import { usePrototypeRead } from './usePrototypeRead';
import './planning.css';

const intervalLabels: Record<EvidenceIntervalState, string> = {
  verificada: 'Verificada', proxima_a_vencer: 'Próxima a vencer', vencida: 'Vencida', declarada: 'Declarada', sin_evidencia: 'Sin evidencia',
};
const kindLabels: Record<SubjectKind, string> = { empresa: 'Empresa', persona: 'Persona', vehiculo: 'Vehículo', equipo: 'Equipo' };

function Detail({ detail }: { detail: DocumentationExplanation }) {
  return <aside className="planning-detail" aria-live="polite"><div className="panel-top"><p className="eyebrow">Detalle del tramo</p><Badge tone={detail.applicability.kind === 'none' ? 'warning' : 'accent'}>{detail.applicability.kind === 'none' ? 'No obligatorio sin contexto' : `Contexto ${detail.applicability.kind.toUpperCase()}`}</Badge></div><h3>{detail.title}</h3><p>{detail.summary}</p><dl><dt>Aplicabilidad</dt><dd>{detail.applicability.label}</dd><dt>Base</dt><dd>{detail.evaluationLabel}</dd></dl><h4>Motivos explicables</h4><ul>{detail.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></aside>;
}

function TimelineRow({ interval, selected, onSelect }: { interval: CalendarInterval; selected: boolean; onSelect: () => void }) {
  const positions: Record<string, [number, number]> = {
    'CAL-EMP-01': [4, 78], 'CAL-PER-01': [18, 34], 'CAL-PER-02': [2, 31], 'CAL-VEH-01': [6, 34], 'CAL-EQP-01': [31, 51], 'CAL-EQP-02': [42, 50],
  };
  const [left, width] = positions[interval.reference] || [10, 45];
  return <div className="timeline-row"><div className="timeline-subject"><span className="subject-kind">{kindLabels[interval.subjectKind]}</span><strong>{interval.subjectLabel}</strong><small>{interval.requirementLabel}</small></div><div className="timeline-track"><span className="today-line" aria-hidden="true" /><button className={`timeline-segment status-${interval.state} ${selected ? 'selected' : ''}`} style={{ left: `${left}%`, width: `${width}%` }} onClick={onSelect} aria-label={`${interval.subjectLabel}, ${interval.requirementLabel}: ${intervalLabels[interval.state]}`}><span>{intervalLabels[interval.state]}</span></button></div></div>;
}

export function CalendarDocumentalScreen({ roles }: { roles: readonly string[] }) {
  const scope = documentationScopeFor(roles);
  const [kind, setKind] = useState<SubjectKind | 'all'>('all');
  const [selected, setSelected] = useState('CAL-PER-01');
  const calendar = usePrototypeRead(() => temporaryMockAccess.readCalendar({ scope, from: '2026-09-01', to: '2026-10-31', subjectKind: kind === 'all' ? undefined : kind }), [scope, kind]);
  const detail = usePrototypeRead(() => temporaryMockAccess.readExplanation({ scope, reference: selected }), [scope, selected]);
  const companyAllowed = scope === 'responsible';
  return <>
    <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Las fechas, sujetos y motivos son ejemplos temporales. No provienen del backend ni reemplazan el contrato pendiente.</p></div></div>
    <section className="panel planning-toolbar"><div><p className="eyebrow">Alcance visible</p><strong>{calendar.data?.scopeLabel || 'Resolviendo alcance del prototipo…'}</strong></div><div className="orientation-tabs" aria-label="Orientación del calendario"><button className={kind === 'all' ? 'active' : ''} onClick={() => setKind('all')}>Todos</button>{(Object.keys(kindLabels) as SubjectKind[]).map(item => <button key={item} disabled={item === 'empresa' && !companyAllowed} title={item === 'empresa' && !companyAllowed ? 'Fuera del alcance de este rol' : undefined} className={kind === item ? 'active' : ''} onClick={() => setKind(item)}>{kindLabels[item]}</button>)}</div></section>
    <div className="planning-legend">{(Object.keys(intervalLabels) as EvidenceIntervalState[]).map(state => <span key={state}><i className={`legend-dot status-${state}`} />{intervalLabels[state]}</span>)}<span className="today-key"><i />Hoy · 21 sep</span></div>
    {calendar.loading ? <LoadingState /> : calendar.error ? <ErrorState message={calendar.error.message} /> : <div className="calendar-layout"><section className="timeline-card" aria-label="Calendario documental"><div className="timeline-scale"><span>1 sep</span><span>15 sep</span><strong>Hoy</strong><span>15 oct</span><span>31 oct</span></div>{calendar.data?.intervals.map(interval => <TimelineRow key={interval.reference} interval={interval} selected={selected === interval.reference} onSelect={() => setSelected(interval.reference)} />)}{calendar.data?.intervals.length === 0 && <p className="empty-inline">No hay tramos temporales en este mock para la orientación elegida.</p>}</section>{detail.loading ? <LoadingState /> : detail.error ? <ErrorState message={detail.error.message} /> : detail.data && <Detail detail={detail.data} />}</div>}
    <section className="module-boundary"><strong>Límite con Módulo 2</strong><span>Sin arrastrar ni asignar recursos</span><span>Sin modificar fechas</span><span>Sin crear OT</span><span>Sin ejecución, tiempos reales, firma ni certificados</span></section>
  </>;
}
