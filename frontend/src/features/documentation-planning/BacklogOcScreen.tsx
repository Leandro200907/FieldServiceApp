import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { importarPlanillaOc } from './realDocumentationPlanningAccess';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { esCargaInicial, usePrototypeRead } from '../../hooks/usePrototypeRead';
import { OcGanttChart, type GanttOcRow } from './OcGanttChart';
import { OcGanttNav } from './OcGanttNav';
import { useGanttViewport } from './useGanttViewport';
import { formatFecha, todayIso } from './dates';
import { lineasDisponibilidad, resumenDocumental, textoAlertaCierta, textoHistorial, tituloQuiebreMapa, vigenciaReprogramacion } from './ocDetail';
import { ListDetailLayout, FichaEncabezado } from '../../ui/ListDetailLayout';
import { StatusDot } from '../../ui/StatusDot';
import { labelEstadoDocumentalOcConMatriz, variantEstadoDocumentalOc } from '../../ui/documentalLabels';
import { NotaAnalisisInformativo } from '../../ui/InformativoFooter';
import './planning.css';
import './timeline.css';

type BacklogItem = components['schemas']['OcBacklogItem'] & { estado_documental?: string | null };
type Cobertura = components['schemas']['CoberturaOcResponse'];
type Catalogos = components['schemas']['CatalogosOcResponse'];
type FilaRechazada = components['schemas']['FilaRechazada'];

function fmtDate(value: string) {
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  return formatFecha(value, tz);
}

function tenantTz() {
  return session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
}

function necesitaCatalogo(motivo: string) {
  const m = motivo.toLowerCase();
  return m.includes('desconocida') || m.includes('desconocido');
}

function itemTieneAlertas(row: BacklogItem): boolean {
  return (row.alertas_ciertas?.length ?? 0) > 0
    || (row.disponibilidad_por_tipo || []).some(d => (d.se_cae_en_ventana?.length ?? 0) > 0);
}

function etiquetaOcContexto(row: BacklogItem): string {
  return [row.operadora_nombre, row.locacion_nombre, row.tipo_servicio_nombre].filter(Boolean).join(' · ');
}

function contarAlertasBacklog(row: BacklogItem): number {
  const ciertas = row.alertas_ciertas?.length ?? 0;
  const caidas = (row.disponibilidad_por_tipo || []).reduce((t, d) => t + (d.se_cae_en_ventana?.length ?? 0), 0);
  return ciertas + caidas;
}

function buildGanttRows(items: BacklogItem[]): GanttOcRow[] {
  return items.map(row => ({
    id: row.clave_origen,
    label: row.clave_origen,
    sublabel: etiquetaOcContexto(row),
    desde: row.vigencia_desde,
    hasta: row.vigencia_hasta,
    reprogramada: row.reprogramada,
    tramosAlerta: (row.alertas_ciertas || []).flatMap(a => (a.tramos as { desde: string; hasta: string }[] | undefined) || []).concat(
      (row.alertas_ciertas || []).filter(a => a.desde && a.hasta).map(a => ({ desde: a.desde!, hasta: a.hasta! })),
    ),
    alertas: (row.disponibilidad_por_tipo || []).flatMap(d =>
      (d.se_cae_en_ventana || []).map(s => {
        const raw = s as { fecha?: string; requisito?: string; nombre?: string };
        const fecha = typeof raw.fecha === 'string' ? raw.fecha : row.vigencia_hasta;
        return {
          fecha,
          titulo: tituloQuiebreMapa({ ...raw, fecha }, d.etiqueta, tenantTz()),
        };
      }),
    ),
  }));
}

type FichaDetalleProps = {
  data: Cobertura;
  puedeReprogramar: boolean;
  reproDesde: string;
  reproHasta: string;
  reproMotivo: string;
  reproError: string | null;
  comparacion: Record<string, unknown> | null;
  ventanaAntes: { desde: string; hasta: string } | null;
  ventanaNueva: { desde: string; hasta: string } | null;
  onReproDesde: (v: string) => void;
  onReproHasta: (v: string) => void;
  onReproMotivo: (v: string) => void;
  onReprogramar: (e: FormEvent) => void;
};

function FichaDetalleCobertura({
  data, puedeReprogramar, reproDesde, reproHasta, reproMotivo, reproError,
  comparacion, ventanaAntes, ventanaNueva, onReproDesde, onReproHasta, onReproMotivo, onReprogramar,
}: FichaDetalleProps) {
  const tz = tenantTz();
  return (
    <>
      <p>{data.tiene_alertas ? 'Con alertas ciertas' : 'Sin alertas ciertas'}</p>
      <div className="backlog-detail-columns">
        <section>
          <h4>Disponibilidad por tipo</h4>
          <ul>
            {(data.disponibilidad_por_tipo || []).map(d => (
              <li key={d.tipo_sujeto}>
                <strong>{d.etiqueta}</strong>
                <ul>
                  {lineasDisponibilidad(d, tz).map(linea => (
                    <li key={linea}>{linea}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
        {(data.alertas_ciertas || []).length > 0 && (
          <section>
            <h4>Alertas ciertas</h4>
            <ul>
              {(data.alertas_ciertas || []).map((a, i) => (
                <li key={`${a.codigo}-${i}`}>{textoAlertaCierta(a, (data.impacto_por_tipo || []) as { tipo_sujeto?: string; dias_sin_habilitados?: number }[], tz)}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
      {comparacion && ventanaAntes && ventanaNueva && (
        <section className="reprog-comparacion">
          <h4>Efecto documental (antes → después)</h4>
          <div>
            <p><strong>Antes</strong> {fmtDate(ventanaAntes.desde)} – {fmtDate(ventanaAntes.hasta)}</p>
            {(() => {
              const r = resumenDocumental(comparacion.documental_anterior as Parameters<typeof resumenDocumental>[0], tz);
              return (
                <>
                  <p>Alertas: {r.alertas.join(' · ')}</p>
                  <p>Impacto: {r.impacto.join(' · ')}</p>
                </>
              );
            })()}
          </div>
          <div>
            <p><strong>Después</strong> {fmtDate(ventanaNueva.desde)} – {fmtDate(ventanaNueva.hasta)}</p>
            {(() => {
              const r = resumenDocumental(comparacion.documental_nuevo as Parameters<typeof resumenDocumental>[0], tz);
              return (
                <>
                  <p>Alertas: {r.alertas.join(' · ')}</p>
                  <p>Impacto: {r.impacto.join(' · ')}</p>
                </>
              );
            })()}
          </div>
          <ul>{((comparacion.mensajes as string[]) || []).map(m => <li key={m}>{m}</li>)}</ul>
        </section>
      )}
      {(data.historial_compromiso || []).length > 0 && (
        <details>
          <summary>Historial de cambios</summary>
          <ul>
            {data.historial_compromiso!.map((h, i) => (
              <li key={i}>{textoHistorial(h as { fecha?: string; origen?: string; motivo?: string }, tz)}</li>
            ))}
          </ul>
        </details>
      )}
      {puedeReprogramar && (
        <form className="form-grid" onSubmit={onReprogramar}>
          <label>Fecha desde<input type="date" value={reproDesde} onChange={e => onReproDesde(e.target.value)} /></label>
          <label>Fecha hasta<input type="date" value={reproHasta} onChange={e => onReproHasta(e.target.value)} /></label>
          <label>Motivo<input value={reproMotivo} onChange={e => onReproMotivo(e.target.value)} /></label>
          <button type="submit" className="button button-secondary">Reprogramar</button>
          {reproError && <p className="field-error" role="alert">{reproError}</p>}
        </form>
      )}
      <Link className="button button-secondary" to={`/timeline-recursos?oc_id=${data.oc.oc_id as string}`}>Ver recursos en el tiempo</Link>
    </>
  );
}

export function BacklogOcScreen({ roles, detailId }: { roles: readonly string[]; detailId?: string }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') || 0);
  const mes = params.get('mes') || '';
  const q = params.get('q') || '';
  const soloAlertas = params.get('solo_con_alertas') === '1';
  const soloReprogramadas = params.get('solo_reprogramadas') === '1';
  const operadoras = params.getAll('operadora_id');
  const vistaMapa = params.get('vista') === 'mapa';
  const selectedId = detailId ?? null;
  const [fichaTab, setFichaTab] = useState<'disponibilidad' | 'mapa'>('disponibilidad');
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [rechazadas, setRechazadas] = useState<FilaRechazada[]>([]);
  const [comparacion, setComparacion] = useState<Record<string, unknown> | null>(null);
  const [ventanaAntes, setVentanaAntes] = useState<{ desde: string; hasta: string } | null>(null);
  const [ventanaNueva, setVentanaNueva] = useState<{ desde: string; hasta: string } | null>(null);
  const [reproDesde, setReproDesde] = useState('');
  const [reproHasta, setReproHasta] = useState('');
  const [reproMotivo, setReproMotivo] = useState('');
  const [reproError, setReproError] = useState<string | null>(null);
  const puedeImportar = roles.includes('responsable_legajos');
  const puedeReprogramar = roles.includes('responsable_legajos') || roles.includes('configuracion');
  const hoy = todayIso();

  const [reloadKey, setReloadKey] = useState(0);
  const catalogosQuery = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/catalogos_oc');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Catalogos;
  }, [reloadKey]);

  const backlogQuery = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/backlog_oc', {
      params: {
        query: {
          offset,
          limit: PAGE_SIZE,
          estado: 'activo',
          mes: mes || undefined,
          q: q || undefined,
          solo_con_alertas: soloAlertas || undefined,
          solo_reprogramadas: soloReprogramadas || undefined,
          ...(operadoras.length ? { operadora_id: operadoras } : {}),
        },
      },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data!;
  }, [offset, mes, q, soloAlertas, soloReprogramadas, operadoras.join(','), reloadKey]);

  const detailQuery = usePrototypeRead(async () => {
    if (!selectedId) return null;
    const { data, error, response } = await session.client.GET('/v1/consultas/cobertura_oc', {
      params: { query: { commitment_id: selectedId } },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Cobertura;
  }, [selectedId, reloadKey]);

  const ocVigenciaDesde = detailQuery.data?.oc?.vigencia_desde as string | undefined;
  const ocVigenciaHasta = detailQuery.data?.oc?.vigencia_hasta as string | undefined;
  const ocIdDetalle = detailQuery.data?.oc?.oc_id as string | undefined;

  useEffect(() => {
    if (!selectedId || !ocVigenciaDesde || !ocVigenciaHasta) return;
    setReproDesde(ocVigenciaDesde);
    setReproHasta(ocVigenciaHasta);
    setReproError(null);
  }, [selectedId, ocIdDetalle, ocVigenciaDesde, ocVigenciaHasta]);

  const items = backlogQuery.data?.items ?? [];

  useEffect(() => {
    const legacyOc = params.get('oc');
    if (!legacyOc || detailId) return;
    const item = items.find(i => i.oc_id === legacyOc || i.clave_origen === legacyOc);
    if (!item) return;
    const next = new URLSearchParams(params);
    next.delete('oc');
    navigate({ pathname: `/backlog-oc/${item.oc_id}`, search: next.toString() }, { replace: true });
  }, [params, detailId, items, navigate]);

  const selectedItem = useMemo(
    () => items.find(i => i.oc_id === selectedId) ?? null,
    [items, selectedId],
  );

  const autoDesde = useMemo(() => {
    if (mes) return `${mes}-01`;
    if (!items.length) return hoy;
    return items.reduce((acc, i) => (i.vigencia_desde < acc ? i.vigencia_desde : acc), items[0].vigencia_desde);
  }, [items, mes, hoy]);

  const autoHasta = useMemo(() => {
    if (mes) {
      const [y, m] = mes.split('-').map(Number);
      const last = new Date(y, m, 0).getDate();
      return `${mes}-${String(last).padStart(2, '0')}`;
    }
    if (!items.length) return hoy;
    return items.reduce((acc, i) => (i.vigencia_hasta > acc ? i.vigencia_hasta : acc), items[0].vigencia_hasta);
  }, [items, mes, hoy]);

  const gantt = useGanttViewport({ hoy, autoDesde, autoHasta });
  const ganttRows = useMemo(() => buildGanttRows(items), [items]);
  const ganttSelectedClave = selectedItem?.clave_origen ?? null;

  const searchSinOc = useMemo(() => {
    const next = new URLSearchParams(params);
    next.delete('oc');
    return next.toString();
  }, [params]);

  const abrirOc = (item: BacklogItem) => {
    const next = new URLSearchParams(params);
    next.delete('vista');
    next.delete('oc');
    navigate({ pathname: `/backlog-oc/${item.oc_id}`, search: next.toString() });
    setFichaTab('disponibilidad');
  };

  const cerrarFicha = () => {
    navigate({ pathname: '/backlog-oc', search: searchSinOc });
  };

  const abrirDesdeGantt = (claveOrigen: string) => {
    const item = items.find(i => i.clave_origen === claveOrigen);
    if (item) abrirOc(item);
  };

  const setVistaMapa = (mapa: boolean) => {
    const next = new URLSearchParams(params);
    if (mapa) {
      next.set('vista', 'mapa');
      navigate({ pathname: '/backlog-oc', search: next.toString() });
    } else {
      next.delete('vista');
      navigate({ pathname: selectedId ? `/backlog-oc/${selectedId}` : '/backlog-oc', search: next.toString() });
    }
  };

  const toggleOperadora = (id: string) => {
    setParams(p => {
      p.delete('offset');
      const cur = p.getAll('operadora_id');
      p.delete('operadora_id');
      if (cur.includes(id)) cur.filter(x => x !== id).forEach(x => p.append('operadora_id', x));
      else [...cur, id].forEach(x => p.append('operadora_id', x));
      return p;
    });
  };

  const onImport = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setImportError('Solo archivos .xlsx');
      setImportMsg(null);
      return;
    }
    setImportError(null);
    setImportMsg(null);
    try {
      const json = await importarPlanillaOc(file);
      const lectura = (json.errores_lectura || []).length;
      setImportMsg(`Aplicadas: ${json.filas_aceptadas} · Rechazadas: ${json.filas_rechazadas}${lectura ? ` · Lectura: ${lectura}` : ''}`);
      setRechazadas(json.detalle_filas_rechazadas ?? []);
      setReloadKey(k => k + 1);
    } catch (err) {
      setRechazadas([]);
      setImportError(err instanceof Error ? err.message : 'No se pudo importar la planilla');
    }
  };

  const onReprogramar = async (e: FormEvent) => {
    e.preventDefault();
    if (!detailQuery.data) return;
    setReproError(null);
    const vigencia = vigenciaReprogramacion(
      { desde: reproDesde, hasta: reproHasta },
      detailQuery.data.oc,
    );
    if (!vigencia.vigencia_desde || !vigencia.vigencia_hasta || !reproMotivo.trim()) {
      setReproError('Completá fecha desde, fecha hasta y motivo');
      return;
    }
    const anterior = {
      desde: detailQuery.data.oc.vigencia_desde as string,
      hasta: detailQuery.data.oc.vigencia_hasta as string,
    };
    const res = await session.client.POST('/v1/comandos/reprogramar_oc', {
      body: {
        oc_id: detailQuery.data.oc.oc_id as string,
        vigencia_desde: vigencia.vigencia_desde,
        vigencia_hasta: vigencia.vigencia_hasta,
        motivo: reproMotivo.trim(),
      },
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    } as never);
    if (res.error || !res.response.ok) {
      setReproError(parseApiError(res.error, res.response, res.response.headers.get('X-Request-ID') || crypto.randomUUID()).message);
      return;
    }
    const body = res.data as { comparacion_documental?: Record<string, unknown> };
    setVentanaAntes(anterior);
    setVentanaNueva({ desde: vigencia.vigencia_desde, hasta: vigencia.vigencia_hasta });
    setComparacion(body.comparacion_documental ?? null);
    setReproMotivo('');
    setReloadKey(k => k + 1);
  };

  const cargaInicial = esCargaInicial(backlogQuery) || esCargaInicial(catalogosQuery);
  if (cargaInicial) return <LoadingState />;
  if (backlogQuery.error && !backlogQuery.data) return <ErrorState message={backlogQuery.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  const operadoraOpts = catalogosQuery.data?.operadoras ?? [];

  const ganttBlock = (
    <>
      <div className="planning-legend gantt-legend">
        <span><i className="legend-dot status-vigente" />Vigente</span>
        <span><i className="legend-dot status-por_vencer" />Por vencer</span>
        <span><i className="legend-dot status-vencido" />Sin cobertura</span>
      </div>
      <OcGanttNav
        zoom={gantt.zoom}
        onZoomChange={gantt.setZoom}
        onAnterior={gantt.anterior}
        onSiguiente={gantt.siguiente}
        onHoy={gantt.irHoy}
        modoAuto={gantt.modoAuto}
        onRestaurarAuto={gantt.usarRangoAutomatico}
      />
      <OcGanttChart
        filas={ganttRows}
        vistaDesde={gantt.vistaDesde}
        vistaHasta={gantt.vistaHasta}
        hoy={hoy}
        selectedId={ganttSelectedClave}
        onSelect={abrirDesdeGantt}
      />
    </>
  );

  const list = (
    <>
      <div className="form-field">
        <label htmlFor="backlog-q">Buscar</label>
        <input id="backlog-q" value={q} onChange={e => setParams(p => { p.set('q', e.target.value); p.delete('offset'); return p; })} placeholder="Número de OC" />
      </div>
      <div className="form-field">
        <label htmlFor="backlog-mes">Mes</label>
        <input id="backlog-mes" type="month" value={mes} onChange={e => setParams(p => { p.set('mes', e.target.value); p.delete('offset'); return p; })} />
      </div>
      <div className="espejo-filter-chips">
        <label className="checkbox-inline">
          <input type="checkbox" checked={soloAlertas} onChange={e => setParams(p => { if (e.target.checked) p.set('solo_con_alertas', '1'); else p.delete('solo_con_alertas'); p.delete('offset'); return p; })} />
          Solo con alertas
        </label>
        <label className="checkbox-inline">
          <input type="checkbox" checked={soloReprogramadas} onChange={e => setParams(p => { if (e.target.checked) p.set('solo_reprogramadas', '1'); else p.delete('solo_reprogramadas'); p.delete('offset'); return p; })} />
          Solo reprogramadas
        </label>
      </div>
      {backlogQuery.loading ? <LoadingState /> : (
        <>
          {items.map(row => (
            <button
              key={row.oc_id}
              type="button"
              className={`list-item-button${selectedId === row.oc_id ? ' selected' : ''}`}
              onClick={() => abrirOc(row)}
            >
              <span>
                <span className="list-item-primary">{row.clave_origen}</span>
                <span className="list-item-secondary">{fmtDate(row.vigencia_desde)} — {fmtDate(row.vigencia_hasta)}</span>
                {etiquetaOcContexto(row) && (
                  <span className="list-item-secondary">{etiquetaOcContexto(row)}</span>
                )}
                {contarAlertasBacklog(row) > 0 && (
                  <span className="list-item-secondary">{contarAlertasBacklog(row)} alerta{contarAlertasBacklog(row) === 1 ? '' : 's'}</span>
                )}
              </span>
              <StatusDot variant={variantEstadoDocumentalOc((row as BacklogItem).estado_documental || '')}>
                {labelEstadoDocumentalOcConMatriz((row as BacklogItem).estado_documental || '', row)}
              </StatusDot>
            </button>
          ))}
          {items.length === 0 && <p className="empty-inline">Sin OC para estos filtros.</p>}
          <PaginationControls offset={offset} limit={PAGE_SIZE} total={backlogQuery.data?.total ?? 0} onOffsetChange={n => setParams(p => { p.set('offset', String(n)); return p; })} />
        </>
      )}
    </>
  );

  const detail = selectedId && (
    detailQuery.loading ? <LoadingState />
      : detailQuery.error ? <ErrorState message={detailQuery.error.message} onRetry={() => setReloadKey(k => k + 1)} />
        : detailQuery.data ? (
          <>
            <FichaEncabezado
              breadcrumb="Backlog de OC / Detalle"
              titulo={detailQuery.data.oc.clave_origen as string}
              subtitulo={`${fmtDate(detailQuery.data.oc.vigencia_desde as string)} – ${fmtDate(detailQuery.data.oc.vigencia_hasta as string)}${selectedItem?.reprogramada ? ' · Reprogramada' : ''}`}
            />
            <div className="ficha-tabs" role="tablist">
              <button type="button" role="tab" className={fichaTab === 'disponibilidad' ? 'active' : ''} aria-selected={fichaTab === 'disponibilidad'} onClick={() => setFichaTab('disponibilidad')}>Disponibilidad</button>
              <button type="button" role="tab" className={fichaTab === 'mapa' ? 'active' : ''} aria-selected={fichaTab === 'mapa'} onClick={() => setFichaTab('mapa')}>Mapa temporal</button>
            </div>
            {fichaTab === 'disponibilidad' ? (
              <FichaDetalleCobertura
                data={detailQuery.data}
                puedeReprogramar={puedeReprogramar}
                reproDesde={reproDesde}
                reproHasta={reproHasta}
                reproMotivo={reproMotivo}
                reproError={reproError}
                comparacion={comparacion}
                ventanaAntes={ventanaAntes}
                ventanaNueva={ventanaNueva}
                onReproDesde={setReproDesde}
                onReproHasta={setReproHasta}
                onReproMotivo={setReproMotivo}
                onReprogramar={onReprogramar}
              />
            ) : ganttBlock}
          </>
        ) : null
  );

  return (
    <div className="planning-layout backlog-oc-shell">
      <header className="panel backlog-oc-filtros">
        <div className="backlog-oc-vista-toggle ficha-tabs">
          <button type="button" className={!vistaMapa ? 'active' : ''} onClick={() => setVistaMapa(false)}>Lista y fichas</button>
          <button type="button" className={vistaMapa ? 'active' : ''} onClick={() => setVistaMapa(true)}>Mapa temporal</button>
        </div>
        <fieldset className="form-field">
          <legend>Operadoras</legend>
          {operadoraOpts.map(o => (
            <label key={o.operadora_id as string}>
              <input type="checkbox" checked={operadoras.includes(o.operadora_id as string)} onChange={() => toggleOperadora(o.operadora_id as string)} />
              {o.nombre as string}
            </label>
          ))}
        </fieldset>
        {puedeImportar && (
          <div className="form-field">
            <label htmlFor="planilla-oc">Importar planilla (Operadora, Locación, Tipo de servicio)</label>
            <input id="planilla-oc" type="file" accept=".xlsx" onChange={e => { const f = e.target.files?.[0]; if (f) void onImport(f); }} />
            {importError && <p className="field-error" role="alert">{importError}</p>}
            {importMsg && <p role="status">{importMsg}</p>}
            {rechazadas.length > 0 && (
              <ul>
                {rechazadas.map(r => (
                  <li key={`${r.indice}-${r.clave_origen}`}>
                    Fila {r.indice}: {r.motivo}
                    {necesitaCatalogo(r.motivo) && (
                      <> — <Link to="/catalogos-oc">Dar de alta en Catálogos</Link></>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <Link className="button button-secondary" to="/catalogos-oc">{roles.includes('responsable_legajos') && !roles.includes('configuracion') ? 'Ver catálogos' : 'Administrar catálogos'}</Link>
      </header>

      {backlogQuery.error && <ErrorState message={backlogQuery.error.message} onRetry={() => setReloadKey(k => k + 1)} />}

      {vistaMapa ? (
        <section className="panel">{ganttBlock}</section>
      ) : (
        <ListDetailLayout listTitle="Órdenes de compra" list={list} detail={detail} onCloseDetail={cerrarFicha} />
      )}

      <NotaAnalisisInformativo />
    </div>
  );
}
