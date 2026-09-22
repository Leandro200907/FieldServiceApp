import { useMemo, useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState, Pending } from '../../ui/States';
import type { ItemCalendario, SubjectKind, VisualCalendarState } from './contracts';
import { deriveVisualState } from './contracts';
import { calendarAccess, isCalendarIntegrated } from './access';
import { addDays, dayPosition, todayIso } from './dates';
import { documentationScopeFor } from './scope';
import { usePrototypeRead } from './usePrototypeRead';
import './planning.css';

const visualStateLabels: Record<VisualCalendarState, string> = { verificada: 'Verificada', vencida: 'Vencida', declarada: 'Declarada' };
const kindLabels: Record<SubjectKind, string> = { empresa: 'Empresa', persona: 'Persona', vehiculo: 'Vehículo', equipo: 'Equipo' };

// Posición proporcional REAL dentro del rango pedido — nunca coordenadas fijas por ítem.
function trackPosition(item: ItemCalendario, from: string, to: string): [number, number] {
  const start = dayPosition(item.vigente_desde, from, to);
  const end = dayPosition(item.vigente_hasta, from, to);
  return [start, Math.max(end - start, 2)];
}

function Detail({ item }: { item: ItemCalendario }) {
  const state = deriveVisualState(item);
  return <aside className="planning-detail" aria-live="polite">
    <div className="panel-top"><p className="eyebrow">Detalle del tramo</p><Badge tone={state === 'vencida' ? 'warning' : 'accent'}>{visualStateLabels[state]}</Badge></div>
    <h3>{item.requisito || 'Requisito sin nombre'} · {item.identificador_natural || item.sujeto_id}</h3>
    <dl>
      <dt>Categoría</dt><dd>{item.categoria}</dd>
      <dt>Vigencia</dt><dd>{item.vigente_desde} — {item.vigente_hasta} ({item.dias_para_vencer >= 0 ? `vence en ${item.dias_para_vencer} días` : `venció hace ${Math.abs(item.dias_para_vencer)} días`})</dd>
      <dt>Confirmación</dt><dd>{item.estado_confirmacion}</dd>
      {item.archivo_validacion && <><dt>Archivo</dt><dd>{item.archivo_validacion}</dd></>}
    </dl>
    <p className="detail-note">Este calendario es general — no confirma si este vencimiento es exigible para ninguna OC. Para eso, consultá la proyección documental de la OC puntual.</p>
  </aside>;
}

function TimelineRow({ item, from, to, todayLeft, selected, onSelect }: { item: ItemCalendario; from: string; to: string; todayLeft: number; selected: boolean; onSelect: () => void }) {
  const state = deriveVisualState(item);
  const [left, width] = trackPosition(item, from, to);
  const label = `${item.identificador_natural || item.sujeto_id}, ${item.requisito || 'requisito'}: ${visualStateLabels[state]}`;
  return <div className="timeline-row">
    <div className="timeline-subject"><span className="subject-kind">{kindLabels[item.tipo_sujeto as SubjectKind] || item.tipo_sujeto}</span><strong>{item.identificador_natural || item.sujeto_id}</strong><small>{item.requisito || '—'}</small></div>
    <div className="timeline-track"><span className="today-line" aria-hidden="true" style={{ left: `${todayLeft}%` }} /><button className={`timeline-segment status-${state} ${selected ? 'selected' : ''}`} style={{ left: `${left}%`, width: `${width}%` }} onClick={onSelect} aria-label={label}><span>{visualStateLabels[state]}</span></button></div>
  </div>;
}

export function CalendarDocumentalScreen({ roles }: { roles: readonly string[] }) {
  const scope = documentationScopeFor(roles);
  const [kind, setKind] = useState<SubjectKind | 'all'>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const from = useMemo(() => todayIso(), []);
  const to = useMemo(() => addDays(from, 40), [from]);
  const calendar = usePrototypeRead(() => calendarAccess().readCalendar({ from, to, subjectKind: kind === 'all' ? undefined : kind }), [from, to, kind]);
  const companyAllowed = scope === 'responsible';
  const integrated = isCalendarIntegrated();
  if (!scope) return <Pending title="Sin rol reconocido para esta vista">Tu sesión no tiene un rol habilitado para el calendario documental.</Pending>;
  const selected = calendar.data?.items.find(item => item.id === selectedId) ?? null;
  // F-01: la marca de "hoy" se ubica con el `hoy` que devuelve el backend (autoridad real
  // sobre la fecha del tenant — F-03), nunca con una posición fija.
  const todayLeft = dayPosition(calendar.data?.hoy ?? from, from, to);
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Calendario general de vencimientos</strong><p>No cruza contra matriz ni OC — no confirma obligatoriedad. Ver proyección documental para eso.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Las fechas, sujetos y motivos son ejemplos temporales. El contrato de forma ya es el real (`docs/openapi.json`); el dato todavía no viene del backend.</p></div></div>}
    <section className="panel planning-toolbar">
      <div><p className="eyebrow">Rango consultado</p><strong>{from} — {to}</strong></div>
      <div className="orientation-tabs" aria-label="Orientación del calendario">
        <button className={kind === 'all' ? 'active' : ''} onClick={() => setKind('all')}>Todos</button>
        {(Object.keys(kindLabels) as SubjectKind[]).map(item => <button key={item} disabled={item === 'empresa' && !companyAllowed} title={item === 'empresa' && !companyAllowed ? 'Fuera del alcance de este rol' : undefined} className={kind === item ? 'active' : ''} onClick={() => setKind(item)}>{kindLabels[item]}</button>)}
      </div>
    </section>
    <div className="planning-legend">{(Object.keys(visualStateLabels) as VisualCalendarState[]).map(state => <span key={state}><i className={`legend-dot status-${state}`} />{visualStateLabels[state]}</span>)}{calendar.data && <span className="today-key"><i />Hoy · {calendar.data.hoy}</span>}</div>
    {calendar.loading ? <LoadingState /> : calendar.error ? <ErrorState message={calendar.error.message} requestId={calendar.error instanceof ApiFailure && calendar.error.detail.referenceSource === 'server' ? calendar.error.detail.requestId : undefined} /> : <div className="calendar-layout">
      <section className="timeline-card" aria-label="Calendario documental">
        <div className="timeline-scale"><span>{from}</span><span>{to}</span></div>
        {calendar.data?.items.map(item => <TimelineRow key={item.id} item={item} from={from} to={to} todayLeft={todayLeft} selected={selectedId === item.id} onSelect={() => setSelectedId(item.id)} />)}
        {calendar.data?.items.length === 0 && <p className="empty-inline">No hay vencimientos registrados en este rango para la orientación elegida.</p>}
      </section>
      {selected && <Detail item={selected} />}
    </div>}
    <section className="module-boundary"><strong>Límite con Módulo 2</strong><span>Sin arrastrar ni asignar recursos</span><span>Sin modificar fechas</span><span>Sin crear OT</span><span>Sin ejecución, tiempos reales, firma ni certificados</span></section>
  </>;
}
