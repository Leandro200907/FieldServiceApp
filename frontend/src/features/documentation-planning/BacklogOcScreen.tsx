import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { importarPlanillaOc } from './realDocumentationPlanningAccess';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { OcGanttChart, type GanttOcRow } from './OcGanttChart';
import { OcGanttNav } from './OcGanttNav';
import { useGanttViewport } from './useGanttViewport';
import './planning.css';
import './timeline.css';

type BacklogItem = components['schemas']['OcBacklogItem'];
type Cobertura = components['schemas']['CoberturaOcResponse'];
type Catalogos = components['schemas']['CatalogosOcResponse'];
type FilaRechazada = components['schemas']['FilaRechazada'];

function fmtDate(value: string) {
  return new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
}

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function necesitaCatalogo(motivo: string) {
  const m = motivo.toLowerCase();
  return m.includes('desconocida') || m.includes('desconocido');
}

export function BacklogOcScreen({ roles }: { roles: readonly string[] }) {
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') || 0);
  const mes = params.get('mes') || '';
  const q = params.get('q') || '';
  const soloAlertas = params.get('solo_con_alertas') === '1';
  const operadoras = params.getAll('operadora_id');
  const selected = params.get('oc') || null;
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [rechazadas, setRechazadas] = useState<FilaRechazada[]>([]);
  const [comparacion, setComparacion] = useState<Record<string, unknown> | null>(null);
  const puedeImportar = roles.includes('responsable_legajos');
  const puedeReprogramar = roles.includes('responsable_legajos') || roles.includes('configuracion');
  const hoy = new Date().toISOString().slice(0, 10);

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
          ...(operadoras.length ? { operadora_id: operadoras } : {}),
        },
      },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data!;
  }, [offset, mes, q, soloAlertas, operadoras.join(','), reloadKey]);

  const detailQuery = usePrototypeRead(async () => {
    if (!selected) return null;
    const { data, error, response } = await session.client.GET('/v1/consultas/cobertura_oc', {
      params: { query: { commitment_id: selected } },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Cobertura;
  }, [selected]);

  const items = backlogQuery.data?.items ?? [];
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

  const ganttRows: GanttOcRow[] = items.map(row => ({
    id: row.clave_origen,
    label: row.clave_origen,
    sublabel: [row.operadora_nombre, row.locacion_nombre].filter(Boolean).join(' · '),
    desde: row.vigencia_desde,
    hasta: row.vigencia_hasta,
    reprogramada: row.reprogramada,
    tramosAlerta: (row.alertas_ciertas || []).flatMap(a => (a.tramos as { desde: string; hasta: string }[] | undefined) || []).concat(
      (row.alertas_ciertas || []).filter(a => a.desde && a.hasta).map(a => ({ desde: a.desde!, hasta: a.hasta! })),
    ),
    alertas: (row.disponibilidad_por_tipo || []).flatMap(d =>
      (d.se_cae_en_ventana || []).map(s => {
        const raw = s as { fecha?: string; requisito?: string };
        const fecha = typeof raw.fecha === 'string' ? raw.fecha : row.vigencia_hasta;
        return {
          fecha,
          titulo: `${raw.fecha ? fmtDate(raw.fecha) : ''} vence ${raw.requisito || 'requisito'} — ${d.etiqueta}`,
        };
      }),
    ),
  }));

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

  if (backlogQuery.loading || catalogosQuery.loading) return <LoadingState />;
  if (backlogQuery.error) return <ErrorState message={backlogQuery.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  const operadoraOpts = catalogosQuery.data?.operadoras ?? [];

  return (
    <div className="planning-layout">
      <header className="panel">
        <p className="eyebrow">Modo consulta</p>
        <h2>Mapa del backlog de OC</h2>
        <p>Alertas ciertas y disponibilidad documental. No asigna recursos ni afirma cobertura.</p>
        <div className="form-row">
          <label>
            Mes
            <input type="month" value={mes} onChange={e => setParams(p => { p.set('mes', e.target.value); p.delete('offset'); return p; })} />
          </label>
          <label>
            Buscar OC
            <input value={q} onChange={e => setParams(p => { p.set('q', e.target.value); p.delete('offset'); return p; })} />
          </label>
          <label>
            <input type="checkbox" checked={soloAlertas} onChange={e => setParams(p => { if (e.target.checked) p.set('solo_con_alertas', '1'); else p.delete('solo_con_alertas'); p.delete('offset'); return p; })} />
            Solo con alertas
          </label>
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
        <Link className="button button-secondary" to="/catalogos-oc">Administrar catálogos</Link>
      </header>

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
        selectedId={selected}
        onSelect={id => setParams(p => { p.set('oc', id); return p; })}
      />

      <PaginationControls offset={offset} limit={PAGE_SIZE} total={backlogQuery.data?.total ?? 0} onOffsetChange={n => setParams(p => { p.set('offset', String(n)); return p; })} />

      {selected && detailQuery.loading && <LoadingState />}
      {selected && detailQuery.data && (
        <section className="panel backlog-detail" aria-live="polite">
          <h3>{detailQuery.data.oc.clave_origen as string}</h3>
          <p>{fmtDate(detailQuery.data.oc.vigencia_desde as string)} – {fmtDate(detailQuery.data.oc.vigencia_hasta as string)}</p>
          <p>{detailQuery.data.tiene_alertas ? 'Con alertas ciertas' : 'Sin alertas'}</p>
          <ul>
            {(detailQuery.data.disponibilidad_por_tipo || []).map(d => (
              <li key={d.tipo_sujeto}>{d.texto}</li>
            ))}
          </ul>
          {comparacion && (
            <section className="reprog-comparacion">
              <h4>Efecto documental (antes → después)</h4>
              <p>Alertas: {String(comparacion.tiene_alertas_antes)} → {String(comparacion.tiene_alertas_despues)}</p>
              <ul>{((comparacion.mensajes as string[]) || []).map(m => <li key={m}>{m}</li>)}</ul>
            </section>
          )}
          {(detailQuery.data.historial_compromiso || []).length > 0 && (
            <details>
              <summary>Historial de cambios</summary>
              <ul>
                {detailQuery.data.historial_compromiso!.map((h, i) => {
                  const row = h as { fecha?: string; origen?: string; motivo?: string };
                  return (
                    <li key={i}>{String(row.fecha ?? '')} · {String(row.origen ?? '')} · {row.motivo || '—'}</li>
                  );
                })}
              </ul>
            </details>
          )}
          {puedeReprogramar && (
            <button
              type="button"
              className="button button-secondary"
              onClick={async () => {
                const motivo = window.prompt('Motivo de reprogramación');
                if (!motivo) return;
                const res = await session.client.POST('/v1/comandos/reprogramar_oc', {
                  body: {
                    oc_id: detailQuery.data!.oc.oc_id as string,
                    vigencia_desde: detailQuery.data!.oc.vigencia_desde as string,
                    vigencia_hasta: addDays(detailQuery.data!.oc.vigencia_hasta as string, 7),
                    motivo,
                  },
                  headers: { 'Idempotency-Key': crypto.randomUUID() },
                } as never);
                if (res.error || !res.response.ok) {
                  window.alert(parseApiError(res.error, res.response, res.response.headers.get('X-Request-ID') || crypto.randomUUID()).message);
                  return;
                }
                const body = res.data as { comparacion_documental?: Record<string, unknown> };
                setComparacion(body.comparacion_documental ?? null);
                setReloadKey(k => k + 1);
              }}
            >
              Reprogramar
            </button>
          )}
          <Link className="button button-secondary" to={`/timeline-recursos?oc_id=${detailQuery.data.oc.oc_id as string}`}>Ver recursos en el tiempo</Link>
        </section>
      )}
    </div>
  );
}
