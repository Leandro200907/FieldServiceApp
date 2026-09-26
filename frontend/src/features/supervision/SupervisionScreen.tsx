import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isSupervisionIntegrated, supervisionAccess } from './access';
import '../documentation-planning/planning.css';
import './supervision.css';

function AssignmentForm({ sujetoId, tieneVigente, onChanged }: { sujetoId: string; tieneVigente: boolean; onChanged: () => void }) {
  const [q, setQ] = useState('');
  const [supervisorId, setSupervisorId] = useState<string | null>(null);
  const [desde, setDesde] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const resultados = usePrototypeRead(() => supervisionAccess().searchSupervisores({ q: q || undefined, limit: 10 }), [q]);

  async function enviar() {
    if (!supervisorId) return;
    setBusy(true); setError(null);
    try {
      if (tieneVigente) await supervisionAccess().reasignarSupervisor(sujetoId, supervisorId, desde || undefined);
      else await supervisionAccess().asignarSupervisor(sujetoId, supervisorId, desde || undefined);
      setSupervisorId(null); setQ(''); setDesde('');
      onChanged();
    } catch (caught) { setError(caught instanceof Error ? caught : new Error('Error desconocido')); }
    finally { setBusy(false); }
  }

  return <section className="panel">
    <h3>{tieneVigente ? 'Reasignar supervisor' : 'Asignar supervisor'}</h3>
    <div className="form-grid">
      <div className="form-field"><label htmlFor="sup-search">Buscar supervisor</label><input id="sup-search" value={q} onChange={event => { setQ(event.target.value); setSupervisorId(null); }} placeholder="Nombre o correo" /></div>
      <div className="form-field"><label htmlFor="sup-desde">Desde (opcional)</label><input id="sup-desde" type="date" value={desde} onChange={event => setDesde(event.target.value)} /></div>
    </div>
    {resultados.data && <ul className="evidence-list">
      {resultados.data.items.map(usuario => <li key={usuario.usuario_id} className="evidence-row">
        <button type="button" className="text-button" onClick={() => setSupervisorId(usuario.usuario_id)}>{usuario.nombre}</button>
        <small>{usuario.email}</small>
        {supervisorId === usuario.usuario_id && <Badge tone="accent">Seleccionado</Badge>}
      </li>)}
      {resultados.data.items.length === 0 && <li className="empty-inline">Sin supervisores que coincidan.</li>}
    </ul>}
    {error && <ErrorState message={error.message} requestId={error instanceof ApiFailure && error.detail.referenceSource === 'server' ? error.detail.requestId : undefined} />}
    <button type="button" className="button button-primary" disabled={!supervisorId || busy} onClick={() => void enviar()}>{tieneVigente ? 'Confirmar reasignación' : 'Confirmar asignación'}</button>
  </section>;
}

export function SupervisionScreen() {
  const [soloVigentes, setSoloVigentes] = useState(true);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [sujetoQuery, setSujetoQuery] = useState('');
  const asignaciones = usePrototypeRead(() => supervisionAccess().readAsignaciones({ soloVigentes, offset, limit: PAGE_SIZE }), [soloVigentes, offset, refreshToken]);
  const busqueda = usePrototypeRead(() => sujetoQuery ? supervisionAccess().searchSujetos({ q: sujetoQuery, limit: 10 }) : Promise.resolve(null), [sujetoQuery]);
  const historial = usePrototypeRead(() => selected ? supervisionAccess().readHistorial({ sujetoId: selected }) : Promise.resolve(null), [selected, refreshToken]);
  const integrated = isSupervisionIntegrated();
  const tieneVigente = Boolean(historial.data?.items.some(item => item.estado === 'vigente'));
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Supervisión</strong><p>Asignación e historial de supervisores.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Asignaciones de ejemplo temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    <section className="panel">
      <div className="form-grid"><div className="form-field checkbox-field"><label htmlFor="sup-vigentes"><input id="sup-vigentes" type="checkbox" checked={soloVigentes} onChange={event => { setSoloVigentes(event.target.checked); setOffset(0); }} /> Solo asignaciones vigentes</label></div></div>
      {asignaciones.loading ? <LoadingState /> : asignaciones.error ? <ErrorState message={asignaciones.error.message} requestId={asignaciones.error instanceof ApiFailure && asignaciones.error.detail.referenceSource === 'server' ? asignaciones.error.detail.requestId : undefined} /> : <>
        <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Sujeto</th><th>Supervisor</th><th>Desde</th><th>Hasta</th><th>Estado</th><th></th></tr></thead><tbody>
          {asignaciones.data?.items.map(item => <tr key={item.asignacion_id}>
            <td>{item.sujeto_id}</td>
            <td>{item.supervisor || item.supervisor_usuario_id}<small>{item.supervisor_email}</small></td>
            <td>{item.desde}</td>
            <td>{item.hasta || 'sin fin'}</td>
            <td><Badge tone={item.estado === 'vigente' ? 'accent' : 'neutral'}>{item.estado}</Badge></td>
            <td><button type="button" className="text-button" onClick={() => setSelected(item.sujeto_id)}>Ver historial</button></td>
          </tr>)}
        </tbody></table></div>
        {asignaciones.data?.items.length === 0 && <p className="empty-inline">Sin asignaciones que coincidan con el filtro.</p>}
        {asignaciones.data && <PaginationControls offset={asignaciones.data.offset} limit={asignaciones.data.limit} total={asignaciones.data.total} onOffsetChange={setOffset} />}
      </>}
    </section>
    <section className="panel">
      <h3>Buscar sujeto</h3>
      <div className="form-field"><label htmlFor="sujeto-search">Nombre o identificador</label><input id="sujeto-search" value={sujetoQuery} onChange={event => setSujetoQuery(event.target.value)} placeholder="Ej: Marina López" /></div>
      {busqueda.data && <ul className="evidence-list">
        {busqueda.data.items.map(sujeto => <li key={sujeto.sujeto_id} className="evidence-row"><button type="button" className="text-button" onClick={() => setSelected(sujeto.sujeto_id)}>{sujeto.identificador_natural}</button><small>{sujeto.tipo_sujeto}</small></li>)}
        {busqueda.data.items.length === 0 && <li className="empty-inline">Sin sujetos que coincidan.</li>}
      </ul>}
    </section>
    {selected && <>
      <section className="panel">
        <h3>Historial de {selected}</h3>
        {historial.loading ? <LoadingState /> : historial.error ? <ErrorState message={historial.error.message} requestId={historial.error instanceof ApiFailure && historial.error.detail.referenceSource === 'server' ? historial.error.detail.requestId : undefined} /> : <>
          <ul className="evidence-list">
            {historial.data?.items.map(item => <li key={item.asignacion_id} className="evidence-row">
              <span className="evidence-name">{item.supervisor_nombre || item.supervisor_usuario_id}</span>
              <Badge tone={item.estado === 'vigente' ? 'accent' : 'neutral'}>{item.estado}</Badge>
              <small>{item.desde} — {item.hasta || 'sin fin'} · asignado por {item.asignada_por}</small>
            </li>)}
          </ul>
          {historial.data?.items.length === 0 && <p className="empty-inline">Sin historial de supervisión para este sujeto.</p>}
        </>}
      </section>
      <AssignmentForm sujetoId={selected} tieneVigente={tieneVigente} onChanged={() => setRefreshToken(token => token + 1)} />
    </>}
  </>;
}
