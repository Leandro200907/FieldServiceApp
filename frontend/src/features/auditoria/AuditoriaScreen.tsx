import { useState } from 'react';
import { ApiFailure, session } from '../../api';
import { ErrorState, LoadingState } from '../../ui/States';
import { formatFechaHora } from '../../ui/fechas';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { auditoriaAccess } from './access';
import { labelTipoEventoAuditoria, tiposEventoAuditoriaOpciones } from './auditoriaLabels';
import type { EventoAuditoria } from './contracts';
import '../documentation-planning/planning.css';
import './auditoria.css';

function toIsoStart(date: string) { return date ? `${date}T00:00:00Z` : undefined; }
function toIsoEnd(date: string) { return date ? `${date}T23:59:59Z` : undefined; }

function detalleLegajoRequisito(payload: Record<string, unknown>): string {
  const partes: string[] = [];
  if (typeof payload.sujeto_id === 'string') partes.push(payload.sujeto_id);
  if (typeof payload.requisito_definicion_id === 'string') partes.push(payload.requisito_definicion_id);
  if (typeof payload.documento_id === 'string' && !partes.length) partes.push(payload.documento_id);
  return partes.length ? partes.join(' · ') : '—';
}

function detalleCambio(payload: Record<string, unknown>): string | null {
  const antes = payload.antes ?? payload.valor_anterior;
  const despues = payload.despues ?? payload.valor_nuevo;
  if (antes !== undefined && despues !== undefined) return `${String(antes)} → ${String(despues)}`;
  if (typeof payload.motivo === 'string') return payload.motivo;
  return null;
}

export function AuditoriaScreen() {
  const [tipo, setTipo] = useState('');
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [offset, setOffset] = useState(0);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const log = usePrototypeRead(() => auditoriaAccess().readLogAuditoria({
    tipo: tipo || undefined, desde: toIsoStart(desde), hasta: toIsoEnd(hasta), offset, limit: PAGE_SIZE,
  }), [tipo, desde, hasta, offset]);

  return <>
    <section className="panel">
      <div className="form-grid">
        <div className="form-field">
          <label htmlFor="audit-tipo">Tipo de evento</label>
          <select id="audit-tipo" value={tipo} onChange={event => { setTipo(event.target.value); setOffset(0); }}>
            <option value="">Todos</option>
            {tiposEventoAuditoriaOpciones.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </div>
        <div className="form-field"><label htmlFor="audit-desde">Desde</label><input id="audit-desde" type="date" value={desde} onChange={event => { setDesde(event.target.value); setOffset(0); }} /></div>
        <div className="form-field"><label htmlFor="audit-hasta">Hasta</label><input id="audit-hasta" type="date" value={hasta} onChange={event => { setHasta(event.target.value); setOffset(0); }} /></div>
      </div>
      {log.loading ? <LoadingState /> : log.error ? <ErrorState message={log.error.message} requestId={log.error instanceof ApiFailure && log.error.detail.referenceSource === 'server' ? log.error.detail.requestId : undefined} /> : <>
        <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Legajo y requisito</th><th>Detalle</th></tr></thead><tbody>
          {log.data?.items.map((evento: EventoAuditoria) => {
            const payload = (evento.payload || {}) as Record<string, unknown>;
            const usuario = evento.usuario_nombre || (payload.usuario_id === 'sistema' ? 'Sistema' : null);
            const detalle = detalleCambio(payload);
            return <tr key={evento.id}>
              <td>{formatFechaHora(evento.ocurrido_en, tz)}</td>
              <td>{usuario ?? '—'}</td>
              <td>{labelTipoEventoAuditoria(evento.tipo)}</td>
              <td className="font-mono">{detalleLegajoRequisito(payload)}</td>
              <td>
                {detalle && <span>{detalle}</span>}
                <details><summary className="text-button">Payload</summary><pre className="audit-payload">{JSON.stringify(evento.payload, null, 2)}</pre></details>
              </td>
            </tr>;
          })}
        </tbody></table></div>
        {log.data?.items.length === 0 && <p className="empty-inline">Sin eventos que coincidan con el filtro.</p>}
        {log.data && <PaginationControls offset={log.data.offset} limit={log.data.limit} total={log.data.total} onOffsetChange={setOffset} />}
      </>}
    </section>
  </>;
}
