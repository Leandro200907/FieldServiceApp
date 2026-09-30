import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { unwrap } from './realDocumentationPlanningAccess';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { OcGanttChart, type GanttOcRow } from './OcGanttChart';
import './planning.css';
import './timeline.css';

type BacklogItem = components['schemas']['OcBacklogItem'];
type Cobertura = components['schemas']['CoberturaOcResponse'];

function fmtDate(value: string) {
  return new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
}

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function BacklogOcScreen({ roles }: { roles: readonly string[] }) {
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') || 0);
  const mes = params.get('mes') || '';
  const q = params.get('q') || '';
  const soloAlertas = params.get('solo_con_alertas') === '1';
  const selected = params.get('oc') || null;
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const puedeImportar = roles.includes('responsable_legajos');
  const puedeReprogramar = roles.includes('responsable_legajos') || roles.includes('configuracion');

  const [reloadKey, setReloadKey] = useState(0);
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
        },
      },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data!;
  }, [offset, mes, q, soloAlertas, reloadKey]);

  const detailQuery = usePrototypeRead(async () => {
    if (!selected) return null;
    const { data, error, response } = await session.client.GET('/v1/consultas/cobertura_oc', {
      params: { query: { commitment_id: selected } },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Cobertura;
  }, [selected]);

  const items = backlogQuery.data?.items ?? [];
  const vistaDesde = mes ? `${mes}-01` : items[0]?.vigencia_desde ?? new Date().toISOString().slice(0, 10);
  const vistaHasta = useMemo(() => {
    if (mes) {
      const [y, m] = mes.split('-').map(Number);
      const last = new Date(y, m, 0).getDate();
      return `${mes}-${String(last).padStart(2, '0')}`;
    }
    const max = items.reduce((acc, i) => (i.vigencia_hasta > acc ? i.vigencia_hasta : acc), vistaDesde);
    return max;
  }, [items, mes, vistaDesde]);

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

  const onImport = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setImportMsg('Solo archivos .xlsx');
      return;
    }
    const loteId = crypto.randomUUID();
    const body = new Uint8Array(await file.arrayBuffer());
    const res = await session.client.POST('/v1/comandos/importar_planilla_oc', {
      params: { query: { lote_id: loteId } },
      body,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'X-Nombre-Archivo': file.name,
      },
    } as never);
    const json = await unwrap(res as never) as { filas_aceptadas: number; filas_rechazadas: number };
    setImportMsg(`Aplicadas: ${json.filas_aceptadas} · Rechazadas: ${json.filas_rechazadas}`);
    setReloadKey(k => k + 1);
  };

  if (backlogQuery.loading) return <LoadingState />;
  if (backlogQuery.error) return <ErrorState message={backlogQuery.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

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
        {puedeImportar && (
          <div className="form-field">
            <label htmlFor="planilla-oc">Importar planilla (Operadora, Locación, Tipo de servicio)</label>
            <input id="planilla-oc" type="file" accept=".xlsx" onChange={e => { const f = e.target.files?.[0]; if (f) void onImport(f); }} />
            {importMsg && <p role="status">{importMsg}</p>}
          </div>
        )}
      </header>

      <OcGanttChart
        filas={ganttRows}
        vistaDesde={vistaDesde}
        vistaHasta={vistaHasta}
        hoy={new Date().toISOString().slice(0, 10)}
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
                await session.client.POST('/v1/comandos/reprogramar_oc', {
                  body: {
                    oc_id: detailQuery.data!.oc.oc_id as string,
                    vigencia_desde: detailQuery.data!.oc.vigencia_desde as string,
                    vigencia_hasta: addDays(detailQuery.data!.oc.vigencia_hasta as string, 7),
                    motivo,
                  },
                  headers: { 'Idempotency-Key': crypto.randomUUID() },
                } as never);
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
