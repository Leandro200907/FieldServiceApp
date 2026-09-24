import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isPropuestasIntegrated, propuestasAccess } from './access';
import type { DocumentoPropuesto } from './contracts';
import '../documentation-planning/planning.css';
import './propuestas.css';

const origenLabels: Record<string, string> = { planilla: 'Planilla', carga_manual: 'Carga manual', drive: 'Drive' };

function ProposalRow({ item, onChanged }: { item: DocumentoPropuesto; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [motivo, setMotivo] = useState('');

  async function confirmar() {
    setBusy(true); setError(null);
    try { await propuestasAccess().confirmarDocumento(item.documento_id); onChanged(); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error('Error desconocido')); }
    finally { setBusy(false); }
  }
  async function rechazar() {
    setBusy(true); setError(null);
    try { await propuestasAccess().rechazarPropuesta(item.documento_id, motivo.trim() || undefined); onChanged(); }
    catch (caught) { setError(caught instanceof Error ? caught : new Error('Error desconocido')); }
    finally { setBusy(false); }
  }

  return <tr>
    <td><strong>{item.sujeto_id}</strong><small>{origenLabels[item.origen] || item.origen}{item.confianza_extraccion ? ` · confianza ${item.confianza_extraccion}` : ''}</small></td>
    <td>{item.requisito || 'Requisito sin nombre'}{item.numero ? <small> · N° {item.numero}</small> : null}</td>
    <td>{item.vigente_desde} — {item.vigente_hasta}</td>
    <td>{item.creado_en.slice(0, 10)}</td>
    <td>
      {error && <ErrorState message={error.message} requestId={error instanceof ApiFailure && error.detail.referenceSource === 'server' ? error.detail.requestId : undefined} />}
      {!rejecting
        ? <div className="proposal-actions"><button type="button" className="button button-primary" disabled={busy} onClick={() => void confirmar()}>Confirmar</button><button type="button" className="button button-secondary" disabled={busy} onClick={() => setRejecting(true)}>Rechazar</button></div>
        : <div className="proposal-reject"><label htmlFor={`motivo-${item.documento_id}`}>Motivo (opcional)</label><input id={`motivo-${item.documento_id}`} value={motivo} onChange={event => setMotivo(event.target.value)} disabled={busy} /><div className="proposal-actions"><button type="button" className="button button-primary" disabled={busy} onClick={() => void rechazar()}>Confirmar rechazo</button><button type="button" className="button button-secondary" disabled={busy} onClick={() => setRejecting(false)}>Cancelar</button></div></div>}
    </td>
  </tr>;
}

export function PropuestasScreen() {
  const [offset, setOffset] = useState(0);
  const [refreshToken, setRefreshToken] = useState(0);
  const bandeja = usePrototypeRead(() => propuestasAccess().readPropuestasPendientes({ offset, limit: PAGE_SIZE }), [offset, refreshToken]);
  const integrated = isPropuestasIntegrated();
  function onChanged() { setRefreshToken(token => token + 1); }
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Revisión documental</strong><p>Documentos propuestos por técnicos, esperando confirmación o rechazo.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Propuestas de ejemplo temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    <div className="availability-warning" role="note"><strong>Sin descarga de evidencia todavía</strong><span>La confirmación/rechazo se decide con los datos declarados; ver el archivo adjunto (G-03) sigue sin integrar.</span></div>
    {bandeja.loading ? <LoadingState /> : bandeja.error ? <ErrorState message={bandeja.error.message} requestId={bandeja.error instanceof ApiFailure && bandeja.error.detail.referenceSource === 'server' ? bandeja.error.detail.requestId : undefined} /> : <>
      <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Sujeto / origen</th><th>Requisito</th><th>Vigencia propuesta</th><th>Propuesto el</th><th>Acción</th></tr></thead><tbody>
        {bandeja.data?.items.map(item => <ProposalRow key={item.documento_id} item={item} onChanged={onChanged} />)}
      </tbody></table></div>
      {bandeja.data?.items.length === 0 && <p className="empty-inline">Sin propuestas pendientes de revisión.</p>}
      {bandeja.data && <PaginationControls offset={bandeja.data.offset} limit={bandeja.data.limit} total={bandeja.data.total} onOffsetChange={setOffset} />}
    </>}
  </>;
}
