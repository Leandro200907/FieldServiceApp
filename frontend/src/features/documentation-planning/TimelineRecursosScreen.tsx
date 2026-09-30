import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import './planning.css';
import './timeline.css';

type Timeline = components['schemas']['TimelineRecursosResponse'];
type Recurso = components['schemas']['RecursoTimeline'];

const VISUAL_LABEL: Record<string, string> = {
  vigente: 'Vigente',
  por_vencer: 'Por vencer',
  vencido: 'Vencido',
  declarado_sin_verificar: 'Declarado sin verificar',
};

function fmtDate(value: string, timeZone?: string) {
  return new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone }).format(new Date(`${value}T12:00:00`));
}

export function TimelineRecursosScreen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const ocId = searchParams.get('oc_id') || undefined;
  const [offset, setOffset] = useState(0);
  const [desde, setDesde] = useState(searchParams.get('desde') || '2026-10-01');
  const [hasta, setHasta] = useState(searchParams.get('hasta') || '2026-11-30');
  const [soloQuiebres, setSoloQuiebres] = useState(false);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';

  const [reloadKey, setReloadKey] = useState(0);
  const query = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/timeline_recursos', {
      params: {
        query: {
          desde, hasta, offset, limit: PAGE_SIZE,
          ...(ocId ? { oc_id: ocId } : {}),
          ...(soloQuiebres ? { solo_quiebres: true } : {}),
        },
      },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Timeline;
  }, [desde, hasta, offset, ocId, soloQuiebres, reloadKey]);

  const hoy = query.data?.hoy;

  const applyRange = () => {
    const next = new URLSearchParams(searchParams);
    next.set('desde', desde);
    next.set('hasta', hasta);
    setSearchParams(next);
    setReloadKey(k => k + 1);
  };

  const rows = query.data?.items ?? [];

  if (query.loading) return <LoadingState />;
  if (query.error) return <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  return <div className="timeline-shell">
    <header className="panel">
      <h2>Timeline de recursos</h2>
      <div className="form-grid">
        <label>Desde<input type="date" value={desde} onChange={e => setDesde(e.target.value)} /></label>
        <label>Hasta<input type="date" value={hasta} onChange={e => setHasta(e.target.value)} /></label>
        <label><input type="checkbox" checked={soloQuiebres} onChange={e => setSoloQuiebres(e.target.checked)} /> Solo con quiebres</label>
        <button type="button" className="button button-primary" onClick={applyRange}>Actualizar</button>
      </div>
      {hoy && <p>Hoy ({tz}): {fmtDate(hoy, tz)}</p>}
    </header>
    <div className="timeline-chart" role="list" aria-label="Recursos y vigencias">
      {rows.map((recurso: Recurso) => (
        <article key={recurso.sujeto_id} className="timeline-row" role="listitem">
          <div className="timeline-row-head">
            <strong>{recurso.identificador}</strong>
            <span>{recurso.tipo_sujeto}</span>
          </div>
          {recurso.tramos.map(tramo => (
            <div
              key={`${tramo.requisito_definicion_id}-${tramo.vigente_desde}`}
              className={`timeline-bar timeline-${tramo.estado_visual}`}
              title={`${tramo.requisito}: ${fmtDate(tramo.vigente_desde, tz)} – ${fmtDate(tramo.vigente_hasta, tz)} (${VISUAL_LABEL[tramo.estado_visual]})`}
              aria-label={`${tramo.requisito}, ${VISUAL_LABEL[tramo.estado_visual] || tramo.estado_visual}, ${fmtDate(tramo.vigente_desde, tz)} a ${fmtDate(tramo.vigente_hasta, tz)}`}
            >
              {tramo.requisito}
            </div>
          ))}
          {recurso.ocs.map(oc => oc.quiebres.map(q => (
            <p key={`${oc.oc_id}-${q.fecha}`} className="timeline-quiebre" role="note">
              Vence {q.requisito} el {fmtDate(q.fecha, tz)} — {oc.clave_origen} ({fmtDate(oc.vigencia_desde, tz)}–{fmtDate(oc.vigencia_hasta, tz)})
            </p>
          )))}
        </article>
      ))}
    </div>
    <PaginationControls offset={offset} limit={PAGE_SIZE} total={query.data?.total ?? 0} onOffsetChange={setOffset} />
  </div>;
}
