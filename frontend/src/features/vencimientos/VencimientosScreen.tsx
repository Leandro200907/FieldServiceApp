import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiFailure, safeFailure, session } from '../../api';
import { formatFecha } from '../documentation-planning/dates';
import { ErrorState, LoadingState } from '../../ui/States';
import { StatusDot, variantFromEtiquetaVigencia } from '../../ui/StatusDot';
import { etiquetaCategoria } from '../../ui/categoriaLabels';
import { espejoLegajoLabel } from './espejoLegajoLabel';
import { lineaPersonaConDni } from '../legajos/legajoDisplay';
import { formatDaysToExpiry } from '../../ui/formatDaysToExpiry';
import { etiquetasEvidencia } from '../../ui/evidenciaPresentacion';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isVencimientosIntegrated, vencimientosAccess } from './access';
import type { ImportarPlanillaOperadorasResponse } from './contracts';
import { HistorialOperadoraPanel } from './HistorialOperadoraPanel';
import '../documentation-planning/planning.css';
import { buildOperadoraFilterOpts, erroresDesdeImportacion, etiquetaFilaImportacion, ordenarErroresImportacion, toggleSearchListParam } from './importacionUi';
import './importacion.css';

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
  const [seccion, setSeccion] = useState<'tablero' | 'espejo'>('tablero');
  const [importAbierto, setImportAbierto] = useState(false);

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

  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const tablero = usePrototypeRead(() => vencimientosAccess().readTableroVencimientos({ dias, offset, limit: PAGE_SIZE }), [dias, offset]);
  const espejo = usePrototypeRead(() => vencimientosAccess().readEspejoOperadora(espejoQuery), [espejoQuery, importRevision]);
  const catalogos = usePrototypeRead(async () => {
    if (!isVencimientosIntegrated()) return { operadoras: [] as { operadora_id: string; nombre: string }[], definiciones: [] as { requisito_definicion_id: string; nombre: string }[] };
    const [ops, defs] = await Promise.all([
      session.client.GET('/v1/consultas/catalogos_oc'),
      session.client.GET('/v1/consultas/definiciones_requisito', { params: { query: { offset: 0, limit: 500 } } }),
    ]);
    if (ops.error || !ops.response.ok) throw new Error('No se pudo cargar el catálogo de operadoras');
    if (defs.error || !defs.response.ok) throw new Error('No se pudo cargar el catálogo de documentos');
    return {
      operadoras: (ops.data?.operadoras ?? []).map(o => ({ operadora_id: String(o.operadora_id), nombre: String(o.nombre) })),
      definiciones: (defs.data?.items ?? []).map(item => ({ requisito_definicion_id: item.requisito_definicion_id, nombre: item.nombre })),
    };
  }, [importRevision]);
  const integrated = isVencimientosIntegrated();
  const puedeImportar = session.getSnapshot().identity?.roles.includes('responsable_legajos') ?? false;
  const erroresPlanilla = errorImportacion ? erroresDesdeImportacion(errorImportacion) : [];

  const operadoraOpts = useMemo(() => {
    const respaldo = new Map<string, string>();
    espejo.data?.items.forEach(item => respaldo.set(item.operadora_id, item.operadora));
    return buildOperadoraFilterOpts(catalogos.data?.operadoras ?? [], params.getAll('operadora_id'), respaldo);
  }, [catalogos.data?.operadoras, espejo.data?.items, params]);

  const requisitoOpts = useMemo(() => {
    const map = new Map((catalogos.data?.definiciones ?? []).map(d => [d.requisito_definicion_id, d.nombre]));
    params.getAll('requisito_definicion_id').forEach(id => {
      if (!map.has(id)) {
        const hit = espejo.data?.items.find(item => item.requisito_definicion_id === id);
        if (hit) map.set(id, hit.requisito);
      }
    });
    return [...map.entries()].map(([requisito_definicion_id, nombre]) => ({ requisito_definicion_id, nombre }))
      .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  }, [catalogos.data?.definiciones, espejo.data?.items, params]);

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
    <div className="ficha-tabs" role="tablist">
      <button type="button" role="tab" className={seccion === 'tablero' ? 'active' : ''} aria-selected={seccion === 'tablero'} onClick={() => setSeccion('tablero')}>Vencimientos</button>
      <button type="button" role="tab" className={seccion === 'espejo' ? 'active' : ''} aria-selected={seccion === 'espejo'} onClick={() => setSeccion('espejo')}>Espejo por operadora</button>
      {puedeImportar && (
        <button type="button" className="button button-secondary vencimientos-import-toggle" onClick={() => setImportAbierto(v => !v)}>Importar presentaciones</button>
      )}
    </div>
    {puedeImportar && importAbierto && <section className="panel">
      <div className="panel-top"><div><p className="eyebrow">Fuente controlada</p><h3>Importar presentaciones de operadoras</h3></div></div>
      <p className="muted">Carga la hoja <strong>Presentaciones</strong>. Cada fila actualiza sólo el espejo de una operadora; no crea ni reemplaza documentos del legajo.</p>
      <div className="import-actions"><a className="button button-secondary" href="/Plantilla_presentaciones_operadoras.xlsx" download>Descargar plantilla</a><input aria-label="Planilla de presentaciones" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={event => { setArchivo(event.target.files?.[0] ?? null); setResultadoImportacion(null); setErrorImportacion(null); }} /><button className="button button-primary" type="button" disabled={!archivo || importando} onClick={() => { void importar(); }}>{importando ? 'Importando…' : 'Importar planilla'}</button></div>
      {resultadoImportacion && <div className={`import-result${resultadoImportacion.filas_rechazadas > 0 ? ' import-result--errors' : ''}`} role={resultadoImportacion.filas_rechazadas > 0 ? 'alert' : 'status'}><strong>{resultadoImportacion.filas_aceptadas} fila{resultadoImportacion.filas_aceptadas === 1 ? '' : 's'} aplicada{resultadoImportacion.filas_aceptadas === 1 ? '' : 's'}</strong><span>{resultadoImportacion.filas_rechazadas} rechazada{resultadoImportacion.filas_rechazadas === 1 ? '' : 's'}.</span>{resultadoImportacion.errores.length > 0 && <ul>{ordenarErroresImportacion(resultadoImportacion.errores).map((error, index) => <li key={`${error.fila ?? 'n'}-${index}`}>{error.mensaje.startsWith('Fila ') ? error.mensaje : `${etiquetaFilaImportacion(error.fila)}: ${error.mensaje}`}</li>)}</ul>}</div>}
      {errorImportacion && <>
        <ErrorState message={errorImportacion.message} requestId={errorImportacion.referenceSource === 'server' ? errorImportacion.requestId : undefined} />
        {erroresPlanilla.length > 0 && <ul className="import-result import-result--errors">{erroresPlanilla.map((error, index) => <li key={`${error.fila ?? 'n'}-${index}`}>{etiquetaFilaImportacion(error.fila)}: {error.mensaje}</li>)}</ul>}
      </>}
    </section>}
    {seccion === 'espejo' && <section className="panel">
      <p className="muted">Compara la versión vigente del legajo con la última versión registrada ante cada operadora.</p>
      <div className="form-grid espejo-filters">
        <div className="form-field"><label htmlFor="espejo-q">Recurso</label><input id="espejo-q" value={params.get('q') || ''} placeholder="Nombre o identificador" onChange={e => patchParams(p => { if (e.target.value) p.set('q', e.target.value); else p.delete('q'); })} /></div>
        <div className="form-field"><label htmlFor="espejo-tipo">Tipo</label><select id="espejo-tipo" value={params.get('tipo_sujeto') || ''} onChange={e => patchParams(p => { if (e.target.value) p.set('tipo_sujeto', e.target.value); else p.delete('tipo_sujeto'); })}>
          <option value="">Todos</option>
          <option value="persona">Persona</option>
          <option value="vehiculo">Vehículo</option>
          <option value="equipo">Equipo</option>
          <option value="empresa">Empresa</option>
        </select></div>
        <div className="form-field"><label htmlFor="espejo-desde">Desde</label><input id="espejo-desde" type="date" value={params.get('movimiento_desde') || ''} onChange={e => patchParams(p => { if (e.target.value) p.set('movimiento_desde', e.target.value); else p.delete('movimiento_desde'); p.delete('mes'); })} /></div>
        <div className="form-field"><label htmlFor="espejo-hasta">Hasta</label><input id="espejo-hasta" type="date" value={params.get('movimiento_hasta') || ''} onChange={e => patchParams(p => { if (e.target.value) p.set('movimiento_hasta', e.target.value); else p.delete('movimiento_hasta'); p.delete('mes'); })} /></div>
        <div className="form-field"><label htmlFor="espejo-mes">Mes</label><input id="espejo-mes" type="month" value={params.get('mes') || ''} onChange={e => patchParams(p => { if (e.target.value) { p.set('mes', e.target.value); p.delete('movimiento_desde'); p.delete('movimiento_hasta'); } else p.delete('mes'); })} /></div>
        <div className="form-field"><label htmlFor="espejo-doc">Documento</label><select id="espejo-doc" value={params.get('requisito_definicion_id') || ''} onChange={e => patchParams(p => {
          p.delete('requisito_definicion_id');
          if (e.target.value) p.append('requisito_definicion_id', e.target.value);
        })}>
          <option value="">Todos</option>
          {requisitoOpts.map(r => <option key={r.requisito_definicion_id} value={r.requisito_definicion_id}>{r.nombre}</option>)}
        </select></div>
      </div>
      <p className="eyebrow">Estado</p>
      <div className="espejo-filter-chips">
        {(['pendiente_envio', 'pendiente_aceptacion', 'rechazado', 'al_dia'] as const).map(estado => (
          <label key={estado} className="checkbox-inline"><input type="checkbox" checked={params.getAll('estado_operadora').includes(estado)} onChange={() => patchParams(p => {
            const cur = p.getAll('estado_operadora');
            p.delete('estado_operadora');
            if (cur.includes(estado)) cur.filter(x => x !== estado).forEach(x => p.append('estado_operadora', x));
            else [...cur, estado].forEach(x => p.append('estado_operadora', x));
          })} /> {ESTADO_ESPEJO_LABELS[estado]}</label>
        ))}
      </div>
      {(operadoraOpts.length > 0 || integrated) && <p className="eyebrow">Operadora</p>}
      {(operadoraOpts.length > 0 || integrated) && <div className="espejo-filter-chips">
        {operadoraOpts.map(o => (
          <label key={o.operadora_id} className="checkbox-inline"><input type="checkbox" checked={params.getAll('operadora_id').includes(o.operadora_id)} onChange={() => patchParams(p => {
            const next = toggleSearchListParam(p, 'operadora_id', o.operadora_id);
            p.delete('operadora_id');
            next.getAll('operadora_id').forEach(x => p.append('operadora_id', x));
          })} /> {o.nombre}</label>
        ))}
      </div>}
      {espejo.loading ? <LoadingState /> : espejo.error ? <ErrorState message={espejo.error.message} requestId={espejo.error instanceof ApiFailure && espejo.error.detail.referenceSource === 'server' ? espejo.error.detail.requestId : undefined} /> : espejo.data?.items.length ?
        <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Legajo</th><th>Documento</th><th>Operadora</th><th>Estado</th><th>Acción requerida</th><th></th></tr></thead><tbody>
          {espejo.data.items.map(item => <tr key={`${item.sujeto_id}-${item.requisito_definicion_id}-${item.operadora_id}`}>
            <td><strong>{espejoLegajoLabel(item)}</strong></td>
            <td>{item.requisito}</td><td>{item.operadora}</td>
            <td><StatusDot variant={item.estado_operadora === 'al_dia' ? 'vigente' : item.estado_operadora === 'rechazado' ? 'vencido' : 'revision'}>{ESTADO_ESPEJO_LABELS[item.estado_operadora] || item.estado_operadora}</StatusDot></td>
            <td>{item.motivo}</td>
            <td><button type="button" className="button button-secondary" onClick={() => setHistorial({ operadoraId: item.operadora_id, sujetoId: item.sujeto_id, requisitoDefinicionId: item.requisito_definicion_id })}>Ver historial</button></td>
          </tr>)}
        </tbody></table></div> : <p className="empty-inline">Sin filas para los filtros actuales.</p>}
      {espejo.data && <PaginationControls offset={espejo.data.offset} limit={espejo.data.limit} total={espejo.data.total} onOffsetChange={setEspejoOffset} />}
    </section>}
    {historial && <HistorialOperadoraPanel {...historial} onClose={() => setHistorial(null)} />}
    {seccion === 'tablero' && <>
    <div className="planning-toolbar">
      <div className="form-field"><p className="eyebrow">Ventana</p><div className="orientation-tabs">{DIAS_OPTIONS.map(option => <button key={option} type="button" className={option === dias ? 'active' : ''} onClick={() => { setDias(option); setOffset(0); }}>{option} días</button>)}</div></div>
      {tablero.data && <div className="form-field"><p className="eyebrow">Hoy</p><strong>{formatFecha(tablero.data.hoy, timeZone)}</strong></div>}
    </div>
    {tablero.loading ? <LoadingState /> : tablero.error ? <ErrorState message={tablero.error.message} requestId={tablero.error instanceof ApiFailure && tablero.error.detail.referenceSource === 'server' ? tablero.error.detail.requestId : undefined} /> : <>
      <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Sujeto</th><th>Requisito</th><th>Categoría</th><th>Vence el</th><th>Estado</th><th>Días</th></tr></thead><tbody>
        {tablero.data?.items.map(item => <tr key={item.id}>
            <td><strong>{lineaPersonaConDni({ tipo_sujeto: (item.tipo_sujeto as 'persona' | 'vehiculo' | 'equipo' | 'empresa') ?? 'persona', nombre_apellido: item.nombre_apellido ?? null, identificador_natural: item.identificador_natural ?? item.sujeto_id, sujeto_id: item.sujeto_id })}</strong></td>
            <td>{item.requisito || 'Requisito sin nombre'}</td>
            <td>{etiquetaCategoria(item.categoria)}</td>
            <td>{formatFecha(item.vigente_hasta, timeZone)}</td>
            <td><span className="estado-tags">{(item.estado_fila ? [item.estado_fila] : etiquetasEvidencia(item)).map(label => <StatusDot key={label} variant={variantFromEtiquetaVigencia(label)}>{label}</StatusDot>)}</span></td>
            <td>{formatDaysToExpiry(item.dias_para_vencer)}</td>
          </tr>)}
      </tbody></table></div>
      {tablero.data?.items.length === 0 && <p className="empty-inline">Sin vencimientos en esta ventana y alcance.</p>}
      {tablero.data && <PaginationControls offset={tablero.data.offset} limit={tablero.data.limit} total={tablero.data.total} onOffsetChange={setOffset} />}
    </>}
    </>}
  </>;
}
