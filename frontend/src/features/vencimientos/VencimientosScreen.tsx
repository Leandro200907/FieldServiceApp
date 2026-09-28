import { useState } from 'react';
import { ApiFailure, safeFailure, session } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { formatDaysToExpiry } from '../../ui/formatDaysToExpiry';
import { deriveVisualState } from '../documentation-planning/contracts';
import type { VisualCalendarState } from '../documentation-planning/contracts';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isVencimientosIntegrated, vencimientosAccess } from './access';
import type { ImportarPlanillaOperadorasResponse } from './contracts';
import '../documentation-planning/planning.css';
import './importacion.css';

const visualStateLabels: Record<VisualCalendarState, string> = { verificada: 'Verificada', vencida: 'Vencida', declarada: 'Declarada' };
const DIAS_OPTIONS = [7, 15, 30, 60, 90];

export function VencimientosScreen() {
  const [dias, setDias] = useState(30);
  const [offset, setOffset] = useState(0);
  const [importRevision, setImportRevision] = useState(0);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [importando, setImportando] = useState(false);
  const [resultadoImportacion, setResultadoImportacion] = useState<ImportarPlanillaOperadorasResponse | null>(null);
  const [errorImportacion, setErrorImportacion] = useState<ReturnType<typeof safeFailure> | null>(null);
  const tablero = usePrototypeRead(() => vencimientosAccess().readTableroVencimientos({ dias, offset, limit: PAGE_SIZE }), [dias, offset]);
  const alertasOperadora = usePrototypeRead(() => vencimientosAccess().readAlertasOperadora({ offset: 0, limit: PAGE_SIZE }), [importRevision]);
  const integrated = isVencimientosIntegrated();
  const puedeImportar = session.getSnapshot().identity?.roles.includes('responsable_legajos') ?? false;
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
      <div className="panel-top"><div><p className="eyebrow">Espejo por operadora</p><h3>Actualizaciones documentales pendientes</h3></div>{alertasOperadora.data && <Badge tone={alertasOperadora.data.total > 0 ? 'warning' : 'accent'}>{alertasOperadora.data.total} pendiente{alertasOperadora.data.total === 1 ? '' : 's'}</Badge>}</div>
      <p className="muted">Compara la versión vigente del legajo con la última versión registrada ante cada operadora.</p>
      {alertasOperadora.loading ? <LoadingState /> : alertasOperadora.error ? <ErrorState message={alertasOperadora.error.message} requestId={alertasOperadora.error instanceof ApiFailure && alertasOperadora.error.detail.referenceSource === 'server' ? alertasOperadora.error.detail.requestId : undefined} /> : alertasOperadora.data?.items.length ?
        <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Legajo</th><th>Documento</th><th>Operadora</th><th>Estado</th><th>Acción requerida</th></tr></thead><tbody>
          {alertasOperadora.data.items.map(item => <tr key={item.alerta_id}>
            <td><strong>{item.identificador_natural}</strong></td><td>{item.requisito}</td><td>{item.operadora}</td>
            <td><Badge tone="warning">{{ pendiente_envio: 'Pendiente de envío', pendiente_aceptacion: 'Pendiente de aceptación', rechazado: 'Rechazado' }[item.estado] || item.estado}</Badge></td>
            <td>{item.motivo}</td>
          </tr>)}
        </tbody></table></div> : <p className="empty-inline">Todas las operadoras registradas tienen la versión documental vigente.</p>}
    </section>
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


