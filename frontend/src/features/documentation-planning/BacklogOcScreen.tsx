import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { unwrap } from './realDocumentationPlanningAccess';
import type { components } from '../../api/generated/modulo1';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import './planning.css';

type BacklogItem = components['schemas']['OcBacklogItem'];
type Cobertura = components['schemas']['CoberturaOcResponse'];

const COBERTURA_LABEL: Record<string, string> = {
  cubierta: 'Cubierta',
  no_cubierta: 'No cubierta',
  sin_matriz: 'Sin matriz',
  empresa_bloquea: 'Empresa bloquea',
};

const TIPO_LABEL: Record<string, string> = {
  persona: 'Personas',
  vehiculo: 'Vehículos',
  equipo: 'Equipos',
};

function fmtDate(value: string) {
  return new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
}

function idsLegibles(cliente: string, locacion: string) {
  return <>Cliente: {cliente} · Locación: {locacion}</>;
}

function resumenTipos(porTipo: BacklogItem['por_tipo']) {
  return porTipo.map(t => {
    const label = TIPO_LABEL[t.tipo_sujeto] || t.tipo_sujeto;
    if (t.estado === 'fuera_de_alcance') return `${label}: fuera de tu alcance`;
    if (t.candidatos_cumplen > 0) return `${label}: ${t.candidatos_cumplen} cumplen`;
    return `${label}: 0 — ${t.motivo || 'sin candidatos'}`;
  }).join(' · ');
}

export function BacklogOcScreen({ roles }: { roles: readonly string[] }) {
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const puedeImportar = roles.includes('responsable_legajos');

  const [reloadKey, setReloadKey] = useState(0);
  const backlogQuery = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/backlog_oc', {
      params: { query: { offset, limit: PAGE_SIZE, estado: 'activo' } },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data!;
  }, [offset, reloadKey]);

  const detailQuery = usePrototypeRead(async () => {
    if (!selected) return null;
    const { data, error, response } = await session.client.GET('/v1/consultas/cobertura_oc', {
      params: { query: { commitment_id: selected } },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Cobertura;
  }, [selected]);

  const onImport = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      setImportMsg('Solo archivos .xlsx');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setImportMsg('Archivo demasiado grande (máx. 5 MiB)');
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

  const items = backlogQuery.data?.items ?? [];
  const badgeTone = useMemo(() => ({
    cubierta: 'accent',
    no_cubierta: 'warning',
    sin_matriz: 'warning',
    empresa_bloquea: 'warning',
  } as const), []);

  if (backlogQuery.loading) return <LoadingState />;
  if (backlogQuery.error) return <ErrorState message={backlogQuery.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  return <div className="planning-layout">
    <header className="panel">
      <p className="eyebrow">Modo consulta</p>
      <h2>Backlog de OC con cobertura</h2>
      <p>Cobertura calculada en vivo. No persiste decisiones ni asigna recursos.</p>
      {puedeImportar && <div className="form-field">
        <label htmlFor="planilla-oc">Importar planilla de OC</label>
        <input id="planilla-oc" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={e => { const f = e.target.files?.[0]; if (f) void onImport(f); }} />
        {importMsg && <p role="status">{importMsg}</p>}
      </div>}
    </header>
    <table className="data-table">
      <thead><tr><th>OC</th><th>Referencia</th><th>Cliente / locación</th><th>Ventana</th><th>Cobertura</th><th>Resumen</th></tr></thead>
      <tbody>
        {items.map(row => (
          <tr key={row.oc_id} className={selected === row.clave_origen ? 'row-selected' : ''}>
            <td><button type="button" className="text-button" onClick={() => setSelected(row.clave_origen)}>{row.clave_origen}</button></td>
            <td>{row.referencia || '—'}</td>
            <td>{idsLegibles(row.cliente_id, row.locacion_id)}</td>
            <td>{fmtDate(row.vigencia_desde)} – {fmtDate(row.vigencia_hasta)}</td>
            <td><Badge tone={badgeTone[row.estado_cobertura as keyof typeof badgeTone] || 'warning'}>{COBERTURA_LABEL[row.estado_cobertura] || row.estado_cobertura}</Badge></td>
            <td>{resumenTipos(row.por_tipo)}</td>
          </tr>
        ))}
      </tbody>
    </table>
    <PaginationControls offset={offset} limit={PAGE_SIZE} total={backlogQuery.data?.total ?? 0} onOffsetChange={setOffset} />
    {selected && detailQuery.loading && <LoadingState />}
    {selected && detailQuery.data && <section className="panel backlog-detail" aria-live="polite">
      <h3>{detailQuery.data.oc.clave_origen}</h3>
      <p>{COBERTURA_LABEL[detailQuery.data.estado_cobertura] || detailQuery.data.estado_cobertura}</p>
      <ul>{detailQuery.data.grupos_candidatos.flatMap(g => g.candidatos.map(c => (
        <li key={c.sujeto_id}>{c.sujeto_id} · {c.asignable ? 'Asignable' : 'No asignable'}{c.primer_quiebre ? ` · quiebre ${c.primer_quiebre}` : ''}</li>
      )))}</ul>
      <Link className="button button-secondary" to={`/timeline-recursos?oc_id=${detailQuery.data.oc.oc_id}`}>Ver en timeline</Link>
    </section>}
  </div>;
}
