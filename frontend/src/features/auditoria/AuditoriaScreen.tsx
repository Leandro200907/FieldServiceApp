import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isAuditoriaIntegrated, auditoriaAccess } from './access';
import '../documentation-planning/planning.css';
import './auditoria.css';

function toIsoStart(date: string) { return date ? `${date}T00:00:00Z` : undefined; }
function toIsoEnd(date: string) { return date ? `${date}T23:59:59Z` : undefined; }

export function AuditoriaScreen() {
  const [tipo, setTipo] = useState('');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [offset, setOffset] = useState(0);
  const log = usePrototypeRead(() => auditoriaAccess().readLogAuditoria({
    tipo: tipo || undefined, desde: toIsoStart(desde), hasta: toIsoEnd(hasta), offset, limit: PAGE_SIZE,
  }), [tipo, desde, hasta, offset]);
  const integrated = isAuditoriaIntegrated();
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Eventos registrados</strong><p>Trazabilidad del tenant, más reciente primero.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Eventos de ejemplo temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    <section className="panel">
      <div className="form-grid">
        <div className="form-field"><label htmlFor="audit-tipo">Tipo de evento</label><input id="audit-tipo" value={tipo} onChange={event => { setTipo(event.target.value); setOffset(0); }} placeholder="Ej: DocumentoConfirmado" /></div>
        <div className="form-field"><label htmlFor="audit-desde">Desde</label><input id="audit-desde" type="date" value={desde} onChange={event => { setDesde(event.target.value); setOffset(0); }} /></div>
        <div className="form-field"><label htmlFor="audit-hasta">Hasta</label><input id="audit-hasta" type="date" value={hasta} onChange={event => { setHasta(event.target.value); setOffset(0); }} /></div>
      </div>
      {log.loading ? <LoadingState /> : log.error ? <ErrorState message={log.error.message} requestId={log.error instanceof ApiFailure && log.error.detail.referenceSource === 'server' ? log.error.detail.requestId : undefined} /> : <>
        <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Fecha</th><th>Tipo</th><th>Evento</th><th>Detalle</th></tr></thead><tbody>
          {log.data?.items.map(evento => <tr key={evento.id}>
            <td>{evento.ocurrido_en.replace('T', ' ').slice(0, 19)}</td>
            <td>{evento.tipo}</td>
            <td>{evento.evento_id}</td>
            <td><details><summary className="text-button">Ver payload</summary><pre className="audit-payload">{JSON.stringify(evento.payload, null, 2)}</pre></details></td>
          </tr>)}
        </tbody></table></div>
        {log.data?.items.length === 0 && <p className="empty-inline">Sin eventos que coincidan con el filtro.</p>}
        {log.data && <PaginationControls offset={log.data.offset} limit={log.data.limit} total={log.data.total} onOffsetChange={setOffset} />}
      </>}
    </section>
  </>;
}
