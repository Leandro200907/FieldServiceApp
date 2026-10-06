import { useEffect, useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState, Pending } from '../../ui/States';
import { formatDaysToExpiry } from '../../ui/formatDaysToExpiry';
import type { ItemCalendario, SubjectKind, VisualCalendarState } from './contracts';
import { deriveVisualState } from './contracts';
import { calendarAccess } from './access';
import { addDays, dayPosition, formatFecha } from './dates';
import { session } from '../../api';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { documentationScopeFor } from './scope';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
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
      <dt>Vigencia</dt><dd>{item.vigente_desde} — {item.vigente_hasta} ({formatDaysToExpiry(item.dias_para_vencer)})</dd>
      <dt>Confirmación</dt><dd>{item.estado_confirmacion}</dd>
      {item.archivo_validacion && <><dt>Archivo</dt><dd>{item.archivo_validacion}</dd></>}
    </dl>
      <p className="detail-note">Este calendario es general: no confirma si este vencimiento es exigible para una OC. Para observar ese cruce informativo, consultá el radar documental.</p>
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

export function CalendarDocumentalScreen({ roles, embedded = false }: { roles: readonly string[]; embedded?: boolean }) {
  const scope = documentationScopeFor(roles);
  const [kind, setKind] = useState<SubjectKind | 'all'>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const fmt = (iso: string) => formatFecha(iso, tz);
  const bootstrapDesde = '2020-01-01';
  const bootstrapHasta = '2035-12-31';
  const [range, setRange] = useState({ from: bootstrapDesde, to: bootstrapHasta });
  const calendar = usePrototypeRead(
    () => calendarAccess().readCalendar({
      from: range.from,
      to: range.to,
      subjectKind: kind === 'all' ? undefined : kind,
      offset,
      limit: PAGE_SIZE,
    }),
    [range.from, range.to, kind, offset],
  );
  useEffect(() => {
    const h = calendar.data?.hoy;
    if (!h) return;
    const next = { from: addDays(h, -30), to: addDays(h, 40) };
    if (range.from === bootstrapDesde && range.to === bootstrapHasta) setRange(next);
  }, [calendar.data?.hoy, range.from, range.to]);
  const from = range.from;
  const to = range.to;
  const setKindAndResetPage = (value: SubjectKind | 'all') => { setKind(value); setOffset(0); };
  const companyAllowed = scope === 'responsible';
  if (!scope) return <Pending title="Sin rol reconocido para esta vista">Tu sesión no tiene un rol habilitado para esta vista.</Pending>;
  const selected = calendar.data?.items.find(item => item.id === selectedId) ?? null;
  // F-01: la marca de "hoy" se ubica con el `hoy` que devuelve el backend (autoridad real
  // sobre la fecha del tenant — F-03), nunca con una posición fija.
  const todayLeft = dayPosition(calendar.data?.hoy ?? from, from, to);
  return <>
    <section className="panel planning-toolbar">
      <div><p className="eyebrow">Rango consultado</p><strong>{fmt(from)} — {fmt(to)}</strong></div>
      <div className="orientation-tabs" aria-label="Orientación del calendario">
        <button className={kind === 'all' ? 'active' : ''} onClick={() => setKindAndResetPage('all')}>Todos</button>
        {(Object.keys(kindLabels) as SubjectKind[]).map(item => <button key={item} disabled={item === 'empresa' && !companyAllowed} title={item === 'empresa' && !companyAllowed ? 'Fuera del alcance de este rol' : undefined} className={kind === item ? 'active' : ''} onClick={() => setKindAndResetPage(item)}>{kindLabels[item]}</button>)}
      </div>
    </section>
    <div className="planning-legend">{(Object.keys(visualStateLabels) as VisualCalendarState[]).map(state => <span key={state}><i className={`legend-dot status-${state}`} />{visualStateLabels[state]}</span>)}{calendar.data && <span className="today-key"><i />Hoy · {fmt(calendar.data.hoy)}</span>}</div>
    {calendar.loading ? <LoadingState /> : calendar.error ? <ErrorState message={calendar.error.message} requestId={calendar.error instanceof ApiFailure && calendar.error.detail.referenceSource === 'server' ? calendar.error.detail.requestId : undefined} /> : <div className="calendar-layout">
      <section className="timeline-card" aria-label="Calendario documental">
        <div className="timeline-scale"><span>{fmt(from)}</span><span>{fmt(to)}</span></div>
        {calendar.data?.items.map(item => <TimelineRow key={item.id} item={item} from={from} to={to} todayLeft={todayLeft} selected={selectedId === item.id} onSelect={() => setSelectedId(item.id)} />)}
        {calendar.data?.items.length === 0 && <p className="empty-inline">No hay vencimientos registrados en este rango para la orientación elegida.</p>}
        {calendar.data && <PaginationControls offset={calendar.data.offset} limit={calendar.data.limit} total={calendar.data.total} onOffsetChange={setOffset} />}
      </section>
      {selected && <Detail item={selected} />}
    </div>}
    {!embedded && <p className="nota-pie-informativa" role="note">Las vigencias mostradas no confirman exigibilidad para una OC concreta.</p>}
  </>;
}


