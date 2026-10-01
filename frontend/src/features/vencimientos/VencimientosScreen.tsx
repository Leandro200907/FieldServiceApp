import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiFailure, safeFailure, session } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { formatDaysToExpiry } from '../../ui/formatDaysToExpiry';
import { deriveVisualState } from '../documentation-planning/contracts';
import type { VisualCalendarState } from '../documentation-planning/contracts';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isVencimientosIntegrated, vencimientosAccess } from './access';
import type { ImportarPlanillaOperadorasResponse } from './contracts';
import { HistorialOperadoraPanel } from './HistorialOperadoraPanel';
import '../documentation-planning/planning.css';
import './importacion.css';

const visualStateLabels: Record<VisualCalendarState, string> = { verificada: 'Verificada', vencida: 'Vencida', declarada: 'Declarada' };
const DIAS_OPTIONS = [7, 15, 30, 60, 90];
const ESTADO_ESPEJO_LABELS: Record<string, string> = {
  pendiente_envio: 'Pendiente de envío',
  pendiente_aceptacion: 'Pendiente de aceptación',
  rechazado: 'Rechazado',
  al_dia: 'Al día',
};

type HistorialTarget = { operadoraId: string; sujetoId: string; requisitoDefinicionId: string };

export function VencimientosScreen() {
  const [params, setParams] = useSearchParams();
  const [dias, setDias] = useState(30);
  const [offset, setOffset] = useState(0);
  const [espejoOffset, setEspejoOffset] = useState(Number(params.get('espejo_offset') || 0));
  const [importRevision, setImportRevision] = useState(0);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [importando, setImportando] = useState(false);
  const [resultadoImportacion, setResultadoImportacion] = useState<ImportarPlanillaOperadorasResponse | null>(null);
  const [errorImportacion, setErrorImportacion] = useState<ReturnType<typeof safeFailure> | null>(null);
  const [historial, setHistorial] = useState<HistorialTarget | null>(null);

  const espejoQuery = useMemo(() => ({
    offset: espejoOffset,
    limit: PAGE_SIZE,
    operadora_id: params.getAll('operadora_id'),
    requisito_definicion_id: params.getAll('requisito_definicion_id'),
    tipo_sujeto: (params.get('tipo_sujeto') || undefined) as 'persona' | 'vehiculo' | 'equipo' | 'empresa' | undefined,
    q: params.get('q') || undefined,
    estado_operadora: params.getAll('estado_operadora') as ('pendiente_envio' | 'pendiente_aceptacion' | 'rechazado' | 'al_dia')[],
    movimiento_desde: params.get('movimiento_desde') || undefined,
    movimiento_hasta: params.get('movimiento_hasta') || undefined,
    mes: params.get('mes') || undefined,
  }), [params, espejoOffset]);

  const tablero = usePrototypeRead(() => vencimientosAccess().readTableroVencimientos({ dias, offset, limit: PAGE_SIZE }), [dias, offset]);
  const espejo = usePrototypeRead(() => vencimientosAccess().readEspejoOperadora(espejoQuery), [espejoQuery, importRevision]);
  const integrated = isVencimientosIntegrated();
  const puedeImportar = session.getSnapshot().identity?.roles.includes('responsable_legajos') ?? false;

  const operadoraOpts = useMemo(() => {
    const map = new Map<string, string>();
    espejo.data?.items.forEach(item => map.set(item.operadora_id, item.operadora));
    return [...map.entries()].map(([operadora_id, nombre]) => ({ operadora_id, nombre }));
  }, [espejo.data?.items]);

  function patchParams(update: (p: URLSearchParams) => void) {
    const next = new URLSearchParams(params);
    update(next);
    next.delete('espejo_offset');
    setEspejoOffset(0);
    setParams(next);
  }

  async function importar() {
    if (!archivo || importando) return;
    setImportando(true); setResultadoImportacion(null); setErrorImportacion(null);
    try {
      const resultado = await vencimientosAccess().importarPlanilla(archivo);
      setResultadoImportacion(resultado); setImportRevision(value => value + 1);
    } catch (error) { setErrorImportacion(safeFailure(error)); }
    finally { setImportando(false); }
  }

  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Tablero de vencimientos</strong><p>Evidencia vigente que vence dentro de la ventana elegida, o ya vencida.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Ítems de ejemplo temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    <div className="availability-warning" role="note"><strong>Solo consulta de vencimientos</strong><span>Sin agregado, políticas, recordatorios ni escalamiento — eso es el ciclo de alertas (H-02), una capacidad distinta.</span></div>
    {puedeImportar && <section className="panel">
      <div className="panel-top"><div><p className="eyebrow">Fuente controlada</p><h3>Importar presentaciones de operadoras</h3></div><Badge>Excel estándar</Badge></div>
      <p className="muted">Carga la hoja <strong>Presentaciones</strong>. Cada fila actualiza sólo el espejo de una operadora; no crea ni reemplaza documentos del legajo.</p>
      <div className="import-actions"><a className="button button-secondary" href="/Plantilla_presentaciones_operadoras.xlsx" download>Descargar plantilla</a><input aria-label="Planilla de presentaciones" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={event => { setArchivo(event.target.files?.[0] ?? null); setResultadoImportacion(null); setErrorImportacion(null); }} /><button className="button button-primary" type="button" disabled={!archivo || importando} onClick={() => { void importar(); }}>{importando ? 'Importando…' : 'Importar planilla'}</button></div>
      {resultadoImportacion && <div className="import-result" role="status"><strong>{resultadoImportacion.filas_aceptadas} fila{resultadoImportacion.filas_aceptadas === 1 ? '' : 's'} aplicada{resultadoImportacion.filas_aceptadas === 1 ? '' : 's'}</strong><span>{resultadoImportacion.filas_rechazadas} rechazada{resultadoImportacion.filas_rechazadas === 1 ? '' : 's'}.</span>{resultadoImportacion.errores.length > 0 && <ul>{resultadoImportacion.errores.map(error => <li key={error.fila}>Fila {error.fila}: {error.mensaje}</li>)}</ul>}</div>}
      {errorImportacion && <ErrorState message={errorImportacion.message} requestId={errorImportacion.referenceSource === 'server' ? errorImportacion.requestId : undefined} />}
    </section>}
    <section className="panel">
      <div className="panel-top"><div><p className="eyebrow">Espejo por operadora</p><h3>Actualizaciones documentales pendientes</h3></div>{espejo.data && <Badge tone={espejo.data.total > 0 ? 'warning' : 'accent'}>{espejo.data.total} fila{espejo.data.total === 1 ? '' : 's'}</Badge>}</div>
      <p className="muted">Compara la versión vigente del legajo con la última versión registrada ante cada operadora.</p>
      <div className="planning-toolbar espejo-filters">
        <label>Recurso<input value={params.get('q') || ''} placeholder="Nombre o identificador" onChange={e => patchParams(p => { if (e.target.value) p.set('q', e.target.value); else p.delete('q'); })} /></label>
        <label>Tipo<select value={params.get('tipo_sujeto') || ''} onChange={e => patchParams(p => { if (e.target.value) p.set('tipo_sujeto', e.target.value); else p.delete('tipo_sujeto'); })}>
          <option value="">Todos</option>
          <option value="persona">Persona</option>
          <option value="vehiculo">Vehículo</option>
          <option value="equipo">Equipo</option>
          <option value="empresa">Empresa</option>
        </select></label>
        <label>Desde<input type="date" value={params.get('movimiento_desde') || ''} onChange={e => patchParams(p => { if (e.target.value) p.set('movimiento_desde', e.target.value); else p.delete('movimiento_desde'); p.delete('mes'); })} /></label>
        <label>Hasta<input type="date" value={params.get('movimiento_hasta') || ''} onChange={e => patchParams(p => { if (e.target.value) p.set('movimiento_hasta', e.target.value); else p.delete('movimiento_hasta'); p.delete('mes'); })} /></label>
        <label>Mes<input type="month" value={params.get('mes') || ''} onChange={e => patchParams(p => { if (e.target.value) { p.set('mes', e.target.value); p.delete('movimiento_desde'); p.delete('movimiento_hasta'); } else p.delete('mes'); })} /></label>
      </div>
      <div className="espejo-filter-chips">
        {(['pendiente_envio', 'pendiente_aceptacion', 'rechazado', 'al_dia'] as const).map(estado => (
          <label key={estado}><input type="checkbox" checked={params.getAll('estado_operadora').includes(estado)} onChange={() => patchParams(p => {
            const cur = p.getAll('estado_operadora');
            p.delete('estado_operadora');
            if (cur.includes(estado)) cur.filter(x => x !== estado).forEach(x => p.append('estado_operadora', x));
            else [...cur, estado].forEach(x => p.append('estado_operadora', x));
          })} /> {ESTADO_ESPEJO_LABELS[estado]}</label>
        ))}
      </div>
      {operadoraOpts.length > 0 && <div className="espejo-filter-chips">
        {operadoraOpts.map(o => (
          <label key={o.operadora_id}><input type="checkbox" checked={params.getAll('operadora_id').includes(o.operadora_id)} onChange={() => patchParams(p => {
            const cur = p.getAll('operadora_id');
            p.delete('operadora_id');
            if (cur.includes(o.operadora_id)) cur.filter(x => x !== o.operadora_id).forEach(x => p.append('operadora_id', x));
            else [...cur, o.operadora_id].forEach(x => p.append('operadora_id', x));
          })} /> {o.nombre}</label>
        ))}
      </div>}
      {espejo.loading ? <LoadingState /> : espejo.error ? <ErrorState message={espejo.error.message} requestId={espejo.error instanceof ApiFailure && espejo.error.detail.referenceSource === 'server' ? espejo.error.detail.requestId : undefined} /> : espejo.data?.items.length ?
        <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Legajo</th><th>Documento</th><th>Operadora</th><th>Estado</th><th>Acción requerida</th><th></th></tr></thead><tbody>
          {espejo.data.items.map(item => <tr key={`${item.sujeto_id}-${item.requisito_definicion_id}-${item.operadora_id}`}>
            <td><strong>{item.identificador_natural}</strong><span className="muted"> · {item.tipo_sujeto}</span></td>
            <td>{item.requisito}</td><td>{item.operadora}</td>
            <td><Badge tone={item.estado_operadora === 'al_dia' ? 'accent' : 'warning'}>{ESTADO_ESPEJO_LABELS[item.estado_operadora] || item.estado_operadora}</Badge></td>
            <td>{item.motivo}</td>
            <td><button type="button" className="button button-secondary" onClick={() => setHistorial({ operadoraId: item.operadora_id, sujetoId: item.sujeto_id, requisitoDefinicionId: item.requisito_definicion_id })}>Ver historial</button></td>
          </tr>)}
        </tbody></table></div> : <p className="empty-inline">Sin filas para los filtros actuales.</p>}
      {espejo.data && <PaginationControls offset={espejo.data.offset} limit={espejo.data.limit} total={espejo.data.total} onOffsetChange={setEspejoOffset} />}
    </section>
    {historial && <HistorialOperadoraPanel {...historial} onClose={() => setHistorial(null)} />}
    <div className="planning-toolbar">
      <div><p className="eyebrow">Ventana</p><div className="orientation-tabs">{DIAS_OPTIONS.map(option => <button key={option} type="button" className={option === dias ? 'active' : ''} onClick={() => { setDias(option); setOffset(0); }}>{option} días</button>)}</div></div>
      {tablero.data && <div><p className="eyebrow">Hoy</p><strong>{tablero.data.hoy}</strong></div>}
    </div>
    {tablero.loading ? <LoadingState /> : tablero.error ? <ErrorState message={tablero.error.message} requestId={tablero.error instanceof ApiFailure && tablero.error.detail.referenceSource === 'server' ? tablero.error.detail.requestId : undefined} /> : <>
      <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Sujeto</th><th>Requisito</th><th>Categoría</th><th>Vence el</th><th>Estado</th><th>Días</th></tr></thead><tbody>
        {tablero.data?.items.map(item => {
          const state = deriveVisualState(item);
          return <tr key={item.id}>
            <td><strong>{item.sujeto_id}</strong></td>
            <td>{item.requisito || 'Requisito sin nombre'}</td>
            <td>{item.categoria || 'Sin categoría'}</td>
            <td>{item.vigente_hasta}</td>
            <td><Badge tone={state === 'vencida' ? 'warning' : 'accent'}>{visualStateLabels[state]}</Badge></td>
            <td>{formatDaysToExpiry(item.dias_para_vencer)}</td>
          </tr>;
        })}
      </tbody></table></div>
      {tablero.data?.items.length === 0 && <p className="empty-inline">Sin vencimientos en esta ventana y alcance.</p>}
      {tablero.data && <PaginationControls offset={tablero.data.offset} limit={tablero.data.limit} total={tablero.data.total} onOffsetChange={setOffset} />}
    </>}
  </>;
}
