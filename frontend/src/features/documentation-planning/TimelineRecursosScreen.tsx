import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { esCargaInicial, usePrototypeRead } from '../../hooks/usePrototypeRead';
import { addDays, formatFecha, todayIso } from './dates';
import { OcGanttChart, type GanttOcRow } from './OcGanttChart';
import { OcGanttNav } from './OcGanttNav';
import { useGanttViewport } from './useGanttViewport';
import './planning.css';
import './timeline.css';

type Timeline = components['schemas']['TimelineRecursosResponse'];
type Recurso = components['schemas']['RecursoTimeline'];

const TONE: Record<string, GanttOcRow['barTone']> = {
  vigente: 'vigente',
  por_vencer: 'por_vencer',
  vencido: 'vencido',
  declarado_sin_verificar: 'declarado_sin_verificar',
};

function fmtDate(value: string, timeZone?: string) {
  return formatFecha(value, timeZone || 'America/Argentina/Buenos_Aires');
}

export function TimelineRecursosScreen() {
  const [searchParams, setSearchParams] = useSearchParams();
  const ocId = searchParams.get('oc_id') || undefined;
  const [offset, setOffset] = useState(0);
  const [desde, setDesde] = useState(searchParams.get('desde') || todayIso());
  const [hasta, setHasta] = useState(searchParams.get('hasta') || addDays(todayIso(), 90));
  const [soloQuiebres, setSoloQuiebres] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
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

  const hoy = query.data?.hoy ?? todayIso();
  const rows = query.data?.items ?? [];

  const autoDesde = useMemo(() => {
    const fechas = rows.flatMap(r => [
      ...r.tramos.map(t => t.vigente_desde),
      ...r.ocs.flatMap(o => [o.vigencia_desde, o.vigencia_hasta]),
    ]).filter(Boolean) as string[];
    if (!fechas.length) return desde;
    return fechas.reduce((a, b) => (a < b ? a : b));
  }, [rows, desde]);

  const autoHasta = useMemo(() => {
    const fechas = rows.flatMap(r => [
      ...r.tramos.map(t => t.vigente_hasta),
      ...r.ocs.flatMap(o => [o.vigencia_desde, o.vigencia_hasta]),
    ]).filter(Boolean) as string[];
    if (!fechas.length) return hasta;
    return fechas.reduce((a, b) => (a > b ? a : b));
  }, [rows, hasta]);

  const gantt = useGanttViewport({ hoy, autoDesde, autoHasta });

  const ganttRows: GanttOcRow[] = useMemo(() => {
    const out: GanttOcRow[] = [];
    for (const recurso of rows as Recurso[]) {
      const sid = recurso.sujeto_id;
      const isOpen = expanded[sid] ?? true;
      const bandasOc = recurso.ocs.map(oc => ({
        desde: oc.vigencia_desde,
        hasta: oc.vigencia_hasta,
        label: oc.clave_origen,
        filtrada: Boolean(ocId && oc.oc_id === ocId),
      }));
      const quiebres = recurso.ocs.flatMap(oc =>
        oc.quiebres.map(q => {
          const verbo = q.tipo === 'inicia' ? 'empieza el' : 'vence el';
          return {
            fecha: q.fecha,
            titulo: `${q.requisito} ${verbo} ${fmtDate(q.fecha, tz)} — ${oc.clave_origen}`,
          };
        }),
      );
      out.push({
        id: sid,
        label: recurso.identificador,
        sublabel: recurso.tipo_sujeto,
        desde: autoDesde,
        hasta: autoHasta,
        bandasOc,
        alertas: quiebres,
        tramosAlerta: [],
        ocultarBarra: true,
      });
      if (isOpen) {
        for (const tramo of recurso.tramos) {
          out.push({
            id: `${sid}-${tramo.requisito_definicion_id}-${tramo.vigente_desde}`,
            label: tramo.requisito || 'Requisito',
            sublabel: tramo.categoria || undefined,
            desde: tramo.vigente_desde,
            hasta: tramo.vigente_hasta,
            alertas: [],
            tramosAlerta: [],
            barTone: TONE[tramo.estado_visual] || 'default',
            indent: 1,
          });
        }
      }
    }
    return out;
  }, [rows, expanded, autoDesde, autoHasta, ocId, tz]);

  const applyRange = () => {
    const next = new URLSearchParams(searchParams);
    next.set('desde', desde);
    next.set('hasta', hasta);
    setSearchParams(next);
    setReloadKey(k => k + 1);
  };

  if (esCargaInicial(query)) return <LoadingState />;
  if (query.error && !query.data) return <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

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
      <Link className="button button-secondary" to="/backlog-oc">Ver mapa del backlog</Link>
    </header>

    {query.loading ? (
      <LoadingState />
    ) : query.error ? (
      <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />
    ) : (
      <>
    <OcGanttNav
      zoom={gantt.zoom}
      onZoomChange={gantt.setZoom}
      onAnterior={gantt.anterior}
      onSiguiente={gantt.siguiente}
      onHoy={gantt.irHoy}
      modoAuto={gantt.modoAuto}
      onRestaurarAuto={gantt.usarRangoAutomatico}
    />

    <div className="timeline-gantt-list">
      {rows.map((recurso: Recurso) => (
        <div key={recurso.sujeto_id} className="timeline-expand-row">
          <button
            type="button"
            className="button button-secondary"
            onClick={() => setExpanded(e => ({ ...e, [recurso.sujeto_id]: !(e[recurso.sujeto_id] ?? true) }))}
          >
            {(expanded[recurso.sujeto_id] ?? true) ? '▾' : '▸'} {recurso.identificador}
          </button>
        </div>
      ))}
    </div>

    <OcGanttChart
      filas={ganttRows}
      vistaDesde={gantt.vistaDesde}
      vistaHasta={gantt.vistaHasta}
      hoy={hoy}
      onSelect={id => {
        if (!id.includes('-')) setExpanded(e => ({ ...e, [id]: !(e[id] ?? true) }));
      }}
    />

    <PaginationControls offset={offset} limit={PAGE_SIZE} total={query.data?.total ?? 0} onOffsetChange={setOffset} />
      </>
    )}
  </div>;
}
