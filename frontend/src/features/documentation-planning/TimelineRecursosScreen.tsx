import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { esCargaInicial, usePrototypeRead } from '../../hooks/usePrototypeRead';
import { addDays, formatFecha } from './dates';
import { lineaPersonaConDni } from '../legajos/legajoDisplay';
import { OcGanttChart, type GanttOcRow } from './OcGanttChart';
import { OcGanttNav } from './OcGanttNav';
import { useGanttViewport } from './useGanttViewport';
import { CalendarDocumentalScreen } from './CalendarDocumentalScreen';
import './planning.css';
import './timeline.css';

type Timeline = components['schemas']['TimelineRecursosResponse'];
type Recurso = components['schemas']['RecursoTimeline'];

const TONE: Record<string, GanttOcRow['barTone']> = {
  vigente: 'vigente',
  por_vencer: 'por_vencer',
  vencido: 'vencido',
  declarado_sin_verificar: 'declarado_sin_verificar',
  sin_archivo_respaldo: 'declarado_sin_verificar',
  archivo_en_revision: 'declarado_sin_verificar',
  evidencia_invalida: 'vencido',
};

function fmtDate(value: string, timeZone?: string) {
  return formatFecha(value, timeZone || 'America/Argentina/Buenos_Aires');
}

export function TimelineRecursosScreen({ roles }: { roles: readonly string[] }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const vista = searchParams.get('vista') === 'documentos' ? 'documentos' : 'recursos';
  const ocId = searchParams.get('oc_id') || undefined;
  const [offset, setOffset] = useState(0);
  const bootstrapDesde = '2020-01-01';
  const bootstrapHasta = '2035-12-31';
  const [desde, setDesde] = useState(searchParams.get('desde') || bootstrapDesde);
  const [hasta, setHasta] = useState(searchParams.get('hasta') || bootstrapHasta);
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

  const hoy = query.data?.hoy ?? '';
  useEffect(() => {
    const anchor = query.data?.hoy;
    if (!anchor || searchParams.get('desde')) return;
    if (desde === bootstrapDesde && hasta === bootstrapHasta) {
      setDesde(addDays(anchor, -30));
      setHasta(addDays(anchor, 90));
    }
  }, [query.data?.hoy, desde, hasta, searchParams]);
  const rows = query.data?.items ?? [];

  const gantt = useGanttViewport({ hoy, autoDesde: desde, autoHasta: hasta });

  const ganttRows: GanttOcRow[] = useMemo(() => {
    const out: GanttOcRow[] = [];
    for (const recurso of rows as Recurso[]) {
      const sid = recurso.sujeto_id;
      const etiquetaLegajo = lineaPersonaConDni({
        tipo_sujeto: recurso.tipo_sujeto,
        nombre_apellido: recurso.nombre_apellido ?? null,
        identificador_natural: recurso.identificador,
        sujeto_id: sid,
      });
      const isOpen = expanded[sid] ?? true;
      const bandasOc = recurso.ocs.map(oc => {
        const ext = oc as {
          operadora_nombre?: string | null;
          locacion_nombre?: string | null;
          servicio_nombre?: string | null;
          estado_oc?: string | null;
        };
        const partes = [
          oc.clave_origen,
          ext.operadora_nombre,
          ext.locacion_nombre,
          ext.servicio_nombre,
          `${fmtDate(oc.vigencia_desde, tz)} – ${fmtDate(oc.vigencia_hasta, tz)}`,
          ext.estado_oc,
        ].filter(Boolean);
        return {
          desde: oc.vigencia_desde,
          hasta: oc.vigencia_hasta,
          label: partes.join(' · '),
          filtrada: Boolean(ocId && oc.oc_id === ocId),
        };
      });
      if (bandasOc.length > 0) {
        out.push({
          id: `${sid}-ocs`,
          label: 'OC vigentes evaluadas',
          sublabel: etiquetaLegajo,
          desde,
          hasta,
          bandasOc,
          alertas: [],
          tramosAlerta: [],
          ocultarBarra: true,
        });
      }
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
        label: etiquetaLegajo,
        sublabel: recurso.tipo_sujeto,
        desde,
        hasta,
        bandasOc: [],
        alertas: quiebres,
        tramosAlerta: [],
        ocultarBarra: true,
      });
      if (isOpen) {
        for (const tramo of recurso.tramos) {
          const enRango = tramo.vigente_hasta >= desde && tramo.vigente_desde <= hasta;
          if (!enRango && tramo.vigente_hasta < desde) continue;
          const toneVigencia = TONE[tramo.estado_visual] ?? (tramo.estado_visual === 'vencido' ? 'vencido' : 'default');
          const confirmado = tramo.estado_confirmacion === 'verificado' || tramo.estado_confirmacion === 'confirmado_en_fuente';
          const tooltipVigente = `${tramo.requisito || 'Requisito'} · ${tramo.estado_visual} · ${fmtDate(tramo.vigente_desde, tz)} – ${fmtDate(tramo.vigente_hasta, tz)} · ${confirmado ? 'Confirmado' : 'Propuesta sin confirmar'}`;
          const sinCoberturaDesde = addDays(tramo.vigente_hasta, 1);
          const segmentos: GanttOcRow['barSegmentos'] = [{
            desde: tramo.vigente_desde,
            hasta: tramo.vigente_hasta,
            barTone: toneVigencia,
            barTooltip: tooltipVigente,
          }];
          if (sinCoberturaDesde <= hasta && tramo.vigente_hasta < hasta) {
            segmentos.push({
              desde: sinCoberturaDesde,
              hasta,
              barTone: 'vencido',
              barTooltip: `${tramo.requisito || 'Requisito'} · Sin cobertura · desde ${fmtDate(sinCoberturaDesde, tz)}`,
            });
          }
          out.push({
            id: `${sid}-${tramo.requisito_definicion_id}-${tramo.vigente_desde}`,
            label: tramo.requisito || 'Requisito',
            sublabel: tramo.categoria || undefined,
            desde: tramo.vigente_desde,
            hasta: segmentos.length > 1 ? hasta : tramo.vigente_hasta,
            alertas: [],
            tramosAlerta: [],
            barSegmentos: segmentos,
            indent: 1,
          });
        }
      }
    }
    return out;
  }, [rows, expanded, desde, hasta, ocId, tz]);

  const applyRange = () => {
    const next = new URLSearchParams(searchParams);
    next.set('desde', desde);
    next.set('hasta', hasta);
    setSearchParams(next);
    setReloadKey(k => k + 1);
  };

  const setVista = (v: 'recursos' | 'documentos') => {
    const next = new URLSearchParams(searchParams);
    if (v === 'documentos') next.set('vista', 'documentos');
    else next.delete('vista');
    setSearchParams(next);
  };

  if (vista === 'documentos') {
    return (
      <div className="timeline-shell">
        <div className="ficha-tabs">
          <button type="button" className="active" onClick={() => setVista('documentos')}>Por documento</button>
          <button type="button" onClick={() => setVista('recursos')}>Por recurso</button>
        </div>
        <CalendarDocumentalScreen roles={roles} embedded />
      </div>
    );
  }

  if (esCargaInicial(query)) return <LoadingState />;
  if (query.error && !query.data) return <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  return (
    <div className="timeline-shell">
      <div className="ficha-tabs">
        <button type="button" className="active" onClick={() => setVista('recursos')}>Por recurso</button>
        <button type="button" onClick={() => setVista('documentos')}>Por documento</button>
      </div>
      <header className="panel">
        <div className="form-grid timeline-range-form">
          <label className="form-field">Desde<input type="date" value={desde} onChange={e => setDesde(e.target.value)} /></label>
          <label className="form-field">Hasta<input type="date" value={hasta} onChange={e => setHasta(e.target.value)} /></label>
          <label className="form-field checkbox-inline"><input type="checkbox" checked={soloQuiebres} onChange={e => setSoloQuiebres(e.target.checked)} /> Con quiebres en el período</label>
          <button type="button" className="button button-primary timeline-range-submit" onClick={applyRange}>Actualizar rango</button>
        </div>
        {hoy && <p className="muted">Hoy: {fmtDate(hoy, tz)}</p>}
      </header>

      <div className="planning-legend gantt-legend">
        <span><i className="legend-dot status-vigente" />Vigente</span>
        <span><i className="legend-dot status-por_vencer" />Por vencer</span>
        <span><i className="legend-dot status-vencido" />Vencido / Sin cobertura</span>
        <span><i className="legend-dot status-declarado_sin_verificar" />Declarado sin verificar</span>
      </div>

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
                  {(expanded[recurso.sujeto_id] ?? true) ? '▾' : '▸'}{' '}
                  {lineaPersonaConDni({
                    tipo_sujeto: recurso.tipo_sujeto,
                    nombre_apellido: recurso.nombre_apellido ?? null,
                    identificador_natural: recurso.identificador,
                    sujeto_id: recurso.sujeto_id,
                  })}
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
    </div>
  );
}
