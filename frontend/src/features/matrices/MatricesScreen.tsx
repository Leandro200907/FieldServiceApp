import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isMatricesIntegrated, matricesAccess } from './access';
import type { MatrizItem } from './contracts';
import '../documentation-planning/planning.css';
import './matrices.css';

const clasificacionLabels: Record<string, string> = { bloqueante_duro: 'Bloqueante duro', excepcionable: 'Excepcionable' };

export function MatricesScreen() {
  const [clienteId, setClienteId] = useState('');
  const [soloVigentes, setSoloVigentes] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<MatrizItem | null>(null);
  const versiones = usePrototypeRead(() => matricesAccess().readMatrices({ clienteId: clienteId || undefined, soloVigentes, offset, limit: PAGE_SIZE }), [clienteId, soloVigentes, offset]);
  const detalle = usePrototypeRead(
    () => selected ? matricesAccess().readMatrizVigente({ clienteId: selected.cliente_id, locacionId: selected.locacion_id, tipoServicioId: selected.tipo_servicio_id, fecha: selected.vigente_desde }) : Promise.resolve(null),
    [selected],
  );
  const integrated = isMatricesIntegrated();
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Matrices documentales</strong><p>Versiones por cliente, locación y tipo de servicio.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Versiones de ejemplo temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    <div className="availability-warning" role="note"><strong>Sin catálogo de nombres todavía</strong><span>Cliente, locación y tipo de servicio se muestran por su identificador — no existe un catálogo que los traduzca a nombre (SEL-09/10/11).</span></div>
    <section className="panel">
      <div className="form-grid">
        <div className="form-field"><label htmlFor="matriz-cliente">Cliente (ID)</label><input id="matriz-cliente" value={clienteId} onChange={event => { setClienteId(event.target.value); setOffset(0); }} placeholder="cliente-norte" /></div>
        <div className="form-field checkbox-field"><label htmlFor="matriz-vigentes"><input id="matriz-vigentes" type="checkbox" checked={soloVigentes} onChange={event => { setSoloVigentes(event.target.checked); setOffset(0); }} /> Solo vigentes hoy</label></div>
      </div>
      {versiones.loading ? <LoadingState /> : versiones.error ? <ErrorState message={versiones.error.message} requestId={versiones.error instanceof ApiFailure && versiones.error.detail.referenceSource === 'server' ? versiones.error.detail.requestId : undefined} /> : <>
        <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Cliente</th><th>Locación</th><th>Tipo de servicio</th><th>Versión</th><th>Vigencia</th><th>Líneas</th><th>Detalle</th></tr></thead><tbody>
          {versiones.data?.items.map(item => <tr key={item.matriz_version_id} className={selected?.matriz_version_id === item.matriz_version_id ? 'selected-row' : ''}>
            <td>{item.cliente_id}</td>
            <td>{item.locacion_id}</td>
            <td>{item.tipo_servicio_id}</td>
            <td>v{item.version}</td>
            <td>{item.vigente_desde} — {item.vigente_hasta || 'sin fin'}</td>
            <td>{item.lineas}</td>
            <td><button type="button" className="text-button" onClick={() => setSelected(item)}>Ver líneas</button></td>
          </tr>)}
        </tbody></table></div>
        {versiones.data?.items.length === 0 && <p className="empty-inline">Sin versiones que coincidan con el filtro.</p>}
        {versiones.data && <PaginationControls offset={versiones.data.offset} limit={versiones.data.limit} total={versiones.data.total} onOffsetChange={setOffset} />}
      </>}
    </section>
    {selected && (detalle.loading ? <LoadingState /> : detalle.error ? <ErrorState message={detalle.error.message} requestId={detalle.error instanceof ApiFailure && detalle.error.detail.referenceSource === 'server' ? detalle.error.detail.requestId : undefined} /> : detalle.data && <section className="panel">
      <h3>Líneas · v{detalle.data.version} · {detalle.data.cliente_id} / {detalle.data.locacion_id} / {detalle.data.tipo_servicio_id}</h3>
      <p className="muted">Consultada al {detalle.data.fecha_consultada} · fuente: {detalle.data.fuente || 'sin registrar'}{detalle.data.autor ? ` · autor: ${detalle.data.autor}` : ''}</p>
      <ul className="evidence-list">
        {detalle.data.lineas.map(linea => <li key={linea.requisito_definicion_id} className="evidence-row">
          <span className="evidence-name">{linea.requisito || 'Requisito sin nombre'}</span>
          <Badge tone={linea.clasificacion === 'bloqueante_duro' ? 'warning' : 'neutral'}>{clasificacionLabels[linea.clasificacion] || linea.clasificacion}</Badge>
          {linea.bloqueante_durante_ejecucion && <Badge tone="warning">Bloqueante en ejecución</Badge>}
          <small>{linea.tipo_sujeto_aplicable || 'Cualquier sujeto'} · {linea.categoria || 'Sin categoría'}</small>
        </li>)}
      </ul>
      {detalle.data.lineas.length === 0 && <p className="empty-inline">Esta versión no tiene líneas.</p>}
    </section>)}
  </>;
}
