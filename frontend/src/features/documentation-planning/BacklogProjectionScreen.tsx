import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState, Pending } from '../../ui/States';
import type { ProjectionState, ProyeccionDocumentalResponse } from './contracts';
import { backlogAccess, isBacklogIntegrated } from './access';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { documentationScopeFor } from './scope';
import { usePrototypeRead } from './usePrototypeRead';
import './planning.css';

const stateLabels: Record<ProjectionState, string> = {
  sin_riesgos_detectados: 'Sin riesgos detectados', riesgo_documental: 'Riesgo documental', bloqueo_confirmado: 'Bloqueo confirmado',
  pendiente_de_planificacion: 'Pendiente de planificación', sin_matriz: 'Sin matriz', requiere_revision: 'Requiere revisión',
  // B-07 (backend): estado propio para una OC cuya vigencia ya terminó — antes reusaba
  // `pendiente_de_planificacion`. Su simetría en el endpoint puntual (segunda revisión
  // externa) hace que este 7º valor aparezca en los dos lugares donde se usa `ProjectionState`.
  vigencia_finalizada: 'Vigencia finalizada',
};
function displayDate(value: string | null | undefined) { return value ? new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: 'short' }).format(new Date(`${value}T12:00:00`)) : 'Sin fecha'; }
function capacityLabel(capacity: Record<string, number>) {
  const entries = Object.entries(capacity);
  if (entries.length === 0) return 'Sin cálculo confirmado';
  return entries.map(([tipo, cantidad]) => `${cantidad} ${tipo}`).join(' · ');
}

function DetailPanel({ detail }: { detail: ProyeccionDocumentalResponse }) {
  return <section className="panel backlog-detail" aria-live="polite">
    <div><p className="eyebrow">Detalle de {detail.commitment_id}</p><h3>{stateLabels[detail.estado]}</h3><p>Ventana evaluada: {detail.desde} — {detail.hasta} (hoy: {detail.hoy})</p></div>
    <div>
      <strong>{detail.sujetos.origen === 'ultima_decision_visible' ? 'Utiliza la última evaluación' : 'Candidatos del alcance (sin decisión visible)'}</strong>
      {detail.causas && <ul>{detail.causas.map((causa, index) => <li key={index}>{causa.motivo}</li>)}</ul>}
      {detail.intervalos.length > 0 && <ul>{detail.intervalos.map((intervalo, index) => <li key={index}>{intervalo.desde} — {intervalo.hasta}: {stateLabels[intervalo.estado]}{intervalo.causas?.map((causa, causaIndex) => <div key={causaIndex} className="detail-note">{causa.motivo}</div>)}</li>)}</ul>}
      {detail.matriz && <p className="muted">Matriz v{detail.matriz.version} · tipos exigidos: {detail.matriz.tipos_exigidos.join(', ') || 'ninguno'}</p>}
    </div>
  </section>;
}

export function BacklogProjectionScreen({ roles }: { roles: readonly string[] }) {
  const resolved = documentationScopeFor(roles);
  const [selected, setSelected] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const projection = usePrototypeRead(() => backlogAccess().readBacklogProjection({ offset, limit: PAGE_SIZE }), [offset]);
  const detail = usePrototypeRead(() => selected ? backlogAccess().readProjectionDetail({ commitmentId: selected }) : Promise.resolve(null), [selected]);
  const integrated = isBacklogIntegrated();
  if (!resolved || resolved === 'technician') return <Pending title="Sin acceso a esta vista">La proyección del backlog es para responsable de legajos y supervisor.</Pending>;
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Proyección documental del backlog</strong><p>Una fila por OC, calculada al momento de la consulta.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Proyección no integrada</strong><p>Una fila por OC con datos de ejemplo. No registra planificación ni confirma recursos.</p></div></div>}
    <div className="availability-warning" role="note"><strong>No garantiza disponibilidad ni asignación operativa</strong><span>Los conteos representan capacidad documental potencial, nunca disponibilidad.</span></div>
    {projection.loading ? <LoadingState /> : projection.error ? <ErrorState message={projection.error.message} requestId={projection.error instanceof ApiFailure && projection.error.detail.referenceSource === 'server' ? projection.error.detail.requestId : undefined} /> : <>
      <section className="panel projection-summary"><div><p className="eyebrow">Hoy</p><strong>{projection.data?.hoy}</strong></div><div><p className="eyebrow">Horizonte</p><strong>{projection.data?.horizonte_dias} días</strong></div><div><p className="eyebrow">Total de OC</p><strong>{projection.data?.total}</strong></div></section>
      <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>OC</th><th>Fechas previstas</th><th>Estado documental</th><th>Primer día de riesgo</th><th>Base de la proyección</th><th>Capacidad documental potencial</th><th>Motivos</th></tr></thead><tbody>
        {projection.data?.items.map(row => <tr key={row.commitment_id} className={selected === row.commitment_id ? 'selected-row' : ''}>
          {/* F-05: antes sólo mostraba `commitment_id` (la clave técnica, `clave_origen`)
              — sin referencia de negocio ni cliente, la tabla era ilegible con datos
              reales. `oc_referencia`/`cliente_id` los suma el backend (B-05). */}
          <td><strong>{row.oc_referencia || row.commitment_id}</strong><small>{row.commitment_id} · {row.cliente_id}</small></td>
          <td>{displayDate(row.vigencia_desde)} — {displayDate(row.vigencia_hasta)}</td>
          <td><span className={`projection-status projection-${row.estado}`}>{stateLabels[row.estado]}</span></td>
          <td>{displayDate(row.primer_quiebre)}</td>
          <td>{row.origen_calculo === 'ultima_decision_visible' ? 'Última evaluación' : 'Candidatos del alcance'}</td>
          <td>{capacityLabel(row.capacidad_documental_potencial_hoy)}</td>
          {/* F-04: el detalle (intervalos, matriz) existe para CUALQUIER estado, no sólo
              cuando hay motivos que resumir — `motivos_resumidos` está vacío justamente
              cuando `estado = sin_riesgos_detectados` (docs/PROYECCION_DOCUMENTAL.md),
              así que condicionar el botón a esa lista dejaba sin forma de abrir el
              detalle de una OC sin riesgo. */}
          <td><button className="text-button" onClick={() => setSelected(row.commitment_id)}>{row.motivos_resumidos.length > 0 ? 'Ver motivos' : 'Ver detalle'}</button></td>
        </tr>)}
      </tbody></table></div>
      {projection.data?.items.length === 0 && <p className="empty-inline">No hay OC visibles en tu alcance para este filtro.</p>}
      {projection.data && <PaginationControls offset={projection.data.offset} limit={projection.data.limit} total={projection.data.total} onOffsetChange={setOffset} />}
    </>}
    {selected && (detail.loading ? <LoadingState /> : detail.error ? <ErrorState message={detail.error.message} /> : detail.data && <DetailPanel detail={detail.data} />)}
    <section className="module-boundary"><strong>Solo proyección documental del Módulo 1</strong><span>Sin disponibilidad</span><span>Sin asignar recursos</span><span>Sin modificar fechas ni crear OT</span><span>Sin ejecución, tiempos reales, firma ni certificados</span></section>
  </>;
}
