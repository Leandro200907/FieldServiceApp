import { useState } from 'react';
import { ApiFailure, session } from '../../api';
import { Badge, ErrorState, LoadingState, Pending } from '../../ui/States';
import type { DetalleOcRadarResponse, ItemRadar, RadarState } from './contracts';
import { backlogAccess, isBacklogIntegrated } from './access';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { documentationScopeFor } from './scope';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import './planning.css';
import './radar.css';

const stateLabels: Record<string, string> = {
  sin_alertas_documentales: 'Sin alertas documentales',
  con_alertas_documentales: 'Con alertas documentales',
  informacion_incompleta: 'Información incompleta',
  sin_matriz: 'Sin matriz aplicable',
  fuera_de_alcance: 'Recursos fuera de tu alcance',
};

function displayDate(value: string | null | undefined) {
  return value ? new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(`${value}T12:00:00`)) : 'Sin fecha';
}

function displayInstant(value: string) {
  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  return new Intl.DateTimeFormat('es-AR', { dateStyle: 'short', timeStyle: 'short', timeZone }).format(new Date(value));
}

function summaryLabel(row: ItemRadar) {
  const alerts = Object.values(row.resumen).reduce((total, item) => total + item.con_alertas, 0);
  const incomplete = Object.values(row.resumen).reduce((total, item) => total + item.incompletos, 0);
  if (alerts === 0 && incomplete === 0) return 'Sin alertas en los legajos observados';
  return [alerts > 0 ? `${alerts} con alerta${alerts === 1 ? '' : 's'}` : '', incomplete > 0 ? `${incomplete} incompleto${incomplete === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ');
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
function asText(value: unknown, fallback = 'Sin dato') { return typeof value === 'string' && value ? value : fallback; }
function asArray(value: unknown) { return Array.isArray(value) ? value : []; }

function DetailPanel({ detail, onLegajo, onOffsetChange }: { detail: DetalleOcRadarResponse; onLegajo: (sujetoId: string) => void; onOffsetChange: (offset: number) => void }) {
  const oc = asRecord(detail.oc);
  return <section className="panel backlog-detail" aria-live="polite">
    <div>
      <p className="eyebrow">Detalle informativo</p>
      <h3>{asText(oc?.clave_origen, 'Orden de compra')}</h3>
      <p>{displayDate(asText(oc?.vigencia_desde, ''))} — {displayDate(asText(oc?.vigencia_hasta, ''))}</p>
      <span className={`projection-status projection-${detail.estado_documental}`}>{stateLabels[detail.estado_documental as RadarState] ?? detail.estado_documental}</span>
      <p className="detail-note">{detail.advertencia}</p>
    </div>
    <div>
      <strong>Matrices y requisitos considerados</strong>
      <p>{detail.matrices_utilizadas.length} tramo{detail.matrices_utilizadas.length === 1 ? '' : 's'} de matriz · {detail.requisitos_particulares.length} requisito{detail.requisitos_particulares.length === 1 ? '' : 's'} particular{detail.requisitos_particulares.length === 1 ? '' : 'es'}.</p>
      <strong>Legajos observados por tipo</strong>
      <ul>
        {detail.grupos.map((rawGroup, groupIndex) => {
          const group = asRecord(rawGroup);
          const legajos = asArray(group?.legajos);
          return <li key={`${asText(group?.tipo_sujeto)}-${groupIndex}`}>
            {asText(group?.tipo_sujeto)}: {legajos.length} en esta página / {typeof group?.total === 'number' ? group.total : legajos.length} en total
            {group?.sin_legajos_requeridos === true && <strong> · Hay recursos de este tipo fuera de tu alcance o sin legajos visibles</strong>}
            {legajos.length > 0 && <ul>{legajos.map((rawLegajo, index) => {
              const legajo = asRecord(rawLegajo);
              const sujetoId = asText(legajo?.sujeto_id, '');
              return <li key={sujetoId || index}>
                {asText(legajo?.identificador_natural, sujetoId || 'Legajo')}
                {' · '}{asText(legajo?.estado_documental)}
                {sujetoId && <button type="button" className="text-button detail-link" onClick={() => onLegajo(sujetoId)}>Ver evidencia</button>}
              </li>;
            })}</ul>}
          </li>;
        })}
      </ul>
      <PaginationControls offset={detail.offset} limit={detail.limit} total={detail.total_legajos} onOffsetChange={onOffsetChange} />
    </div>
  </section>;
}

export function RadarDocumentalScreen({ roles }: { roles: readonly string[] }) {
  const resolved = documentationScopeFor(roles);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedLegajo, setSelectedLegajo] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [detailOffset, setDetailOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [state, setState] = useState<RadarState | ''>('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [appliedState, setAppliedState] = useState<RadarState | ''>('');

  const radar = usePrototypeRead(
    () => backlogAccess().readRadarBacklog({ q: appliedSearch || undefined, estado: appliedState ? [appliedState] : undefined, offset, limit: PAGE_SIZE }),
    [appliedSearch, appliedState, offset],
  );
  const detail = usePrototypeRead(() => selected ? backlogAccess().readRadarOc({ ocId: selected, offset: detailOffset, limit: PAGE_SIZE }) : Promise.resolve(null), [selected, detailOffset]);
  const legajo = usePrototypeRead(
    () => selected && selectedLegajo ? backlogAccess().readRadarLegajo({ ocId: selected, sujetoId: selectedLegajo }) : Promise.resolve(null),
    [selected, selectedLegajo],
  );
  const integrated = isBacklogIntegrated();

  if (!resolved || resolved === 'technician') return <Pending title="Sin acceso a esta vista">El radar documental del backlog está disponible para responsables de legajos y supervisores.</Pending>;

  function applyFilters() {
    setOffset(0);
    setSelected(null);
    setSelectedLegajo(null);
    setDetailOffset(0);
    setAppliedSearch(search.trim());
    setAppliedState(state);
  }

  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Radar documental del backlog</strong><p>Todas las OC visibles se comparan con la información documental registrada.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Radar documental de ejemplo</strong><p>No registra planificación ni confirma recursos.</p></div></div>}

    <div className="availability-warning" role="note"><strong>Lectura informativa, no planificación</strong><span>El radar identifica señales documentales usando las fechas previstas de cada OC. No asigna, recomienda ni confirma disponibilidad de personas, vehículos o equipos.</span></div>

    <section className="panel">
      <div className="form-grid">
        <div className="form-field"><label htmlFor="radar-search">Buscar OC</label><input id="radar-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Número o referencia" /></div>
        <div className="form-field"><label htmlFor="radar-state">Estado documental</label><select id="radar-state" value={state} onChange={event => setState(event.target.value as RadarState | '')}><option value="">Todos</option>{Object.entries(stateLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      </div>
      <button type="button" className="button button-primary" onClick={applyFilters}>Aplicar filtros</button>
    </section>

    {radar.loading ? <LoadingState /> : radar.error ? <ErrorState message={radar.error.message} requestId={radar.error instanceof ApiFailure && radar.error.detail.referenceSource === 'server' ? radar.error.detail.requestId : undefined} /> : <>
      <section className="panel projection-summary"><div><p className="eyebrow">Ventana observada</p><strong>{displayDate(radar.data?.desde)} — {displayDate(radar.data?.hasta)}</strong></div><div><p className="eyebrow">OC visibles</p><strong>{radar.data?.total}</strong></div><div><p className="eyebrow">Calculado</p><strong>{radar.data ? displayInstant(radar.data.calculado_en) : '—'}</strong></div></section>
      <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>OC</th><th>Ejecución prevista</th><th>Contexto documental</th><th>Estado</th><th>Primera señal</th><th>Resumen informativo</th><th></th></tr></thead><tbody>
        {radar.data?.items.map(row => <tr key={row.oc_id} className={selected === row.oc_id ? 'selected-row' : ''}>
          <td><strong>{row.clave_origen}</strong><small>{row.referencia || row.oc_id}</small></td>
          <td>{displayDate(row.vigencia_desde)} — {displayDate(row.vigencia_hasta)}</td>
          <td><span>{row.cliente_id}</span><small>{row.locacion_id} · {row.tipo_servicio_id}</small></td>
          <td><span className={`projection-status projection-${row.estado_documental}`}>{stateLabels[row.estado_documental]}</span></td>
          <td>{displayDate(row.primer_quiebre)}</td>
          <td>{row.motivos_resumidos.length > 0 ? row.motivos_resumidos.join(' · ') : summaryLabel(row)}</td>
          <td><button type="button" className="text-button" onClick={() => { setSelected(row.oc_id); setSelectedLegajo(null); setDetailOffset(0); }}>Ver detalle</button></td>
        </tr>)}
      </tbody></table></div>
      {radar.data?.items.length === 0 && <p className="empty-inline">No hay OC visibles para estos filtros.</p>}
      {radar.data && <PaginationControls offset={radar.data.offset} limit={radar.data.limit} total={radar.data.total} onOffsetChange={value => { setOffset(value); setSelected(null); setSelectedLegajo(null); }} />}
      {radar.data?.advertencia && <p className="detail-note">{radar.data.advertencia}</p>}
    </>}

    {selected && (detail.loading ? <LoadingState /> : detail.error ? <ErrorState message={detail.error.message} /> : detail.data && <DetailPanel detail={detail.data} onLegajo={setSelectedLegajo} onOffsetChange={value => { setDetailOffset(value); setSelectedLegajo(null); }} />)}
    {selectedLegajo && (legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} /> : legajo.data && <section className="panel" aria-live="polite"><p className="eyebrow">Evidencia del legajo en esta OC</p><h3>{asText(asRecord(legajo.data.legajo)?.identificador_natural, selectedLegajo)}</h3><p>Estado: {asText(asRecord(legajo.data.legajo)?.estado_documental)}</p><p>{asArray(asRecord(legajo.data.legajo)?.requisitos).length} requisito{asArray(asRecord(legajo.data.legajo)?.requisitos).length === 1 ? '' : 's'} evaluado{asArray(asRecord(legajo.data.legajo)?.requisitos).length === 1 ? '' : 's'}.</p><p className="detail-note">{legajo.data.advertencia}</p></section>)}

    <section className="module-boundary"><strong>Límite del Módulo 1</strong><span>Sin disponibilidad</span><span>Sin candidatos</span><span>Sin asignar recursos</span><span>Sin modificar fechas ni crear OT</span></section>
  </>;
}

