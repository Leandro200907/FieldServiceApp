import { useRef, useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { propuestasAccess } from './access';
import { subtituloLegajoPersona, tituloLegajoPersona } from '../legajos/legajoDisplay';
import { session } from '../../api';
import { formatFecha, formatFechaHora } from '../../ui/fechas';
import type { DocumentoPropuesto } from './contracts';
import type { PropuestasAccess } from './contracts';
import '../documentation-planning/planning.css';
import './propuestas.css';

const origenLabels: Record<string, string> = { planilla: 'Planilla', carga_manual: 'Propuesta del técnico', drive: 'Drive' };

function ProposalRow({ item, onChanged, access, readOnly }: { item: DocumentoPropuesto; onChanged: () => void; access: PropuestasAccess; readOnly: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [motivo, setMotivo] = useState('');
  const confirmarKey = useRef<string | null>(null);
  const rechazarIntent = useRef<{ motivo: string; key: string } | null>(null);

  function respuestaDefinitiva(error: unknown) {
    return error instanceof ApiFailure && error.detail.status > 0;
  }

  async function confirmar() {
    setBusy(true); setError(null);
    confirmarKey.current ??= crypto.randomUUID();
    try { await access.confirmarDocumento(item.documento_id, confirmarKey.current); confirmarKey.current = null; onChanged(); }
    catch (caught) { if (respuestaDefinitiva(caught)) confirmarKey.current = null; setError(caught instanceof Error ? caught : new Error('Error desconocido')); }
    finally { setBusy(false); }
  }
  async function rechazar() {
    setBusy(true); setError(null);
    const motivoNormalizado = motivo.trim();
    if (!motivoNormalizado) { setBusy(false); return; }
    if (!rechazarIntent.current || rechazarIntent.current.motivo !== motivoNormalizado) {
      rechazarIntent.current = { motivo: motivoNormalizado, key: crypto.randomUUID() };
    }
    try { await access.rechazarPropuesta(item.documento_id, motivoNormalizado, rechazarIntent.current.key); rechazarIntent.current = null; onChanged(); }
    catch (caught) { if (respuestaDefinitiva(caught)) rechazarIntent.current = null; setError(caught instanceof Error ? caught : new Error('Error desconocido')); }
    finally { setBusy(false); }
  }

  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const sujeto = {
    tipo_sujeto: item.tipo_sujeto ?? 'persona',
    nombre_apellido: item.nombre_apellido ?? null,
    identificador_natural: item.identificador_natural ?? item.sujeto_id,
  };
  return <tr>
    <td><strong>{tituloLegajoPersona(sujeto)}</strong>{subtituloLegajoPersona(sujeto) && <small><br />{subtituloLegajoPersona(sujeto)}</small>}<small>{origenLabels[item.origen] || item.origen}{item.confianza_extraccion ? ` · confianza ${item.confianza_extraccion}` : ''}</small></td>
    <td>{item.requisito || 'Requisito sin nombre'}{item.numero ? <small> · N° {item.numero}</small> : null}</td>
    <td>{formatFecha(item.vigente_desde, tz)} — {formatFecha(item.vigente_hasta, tz)}</td>
    <td>{formatFechaHora(item.creado_en, tz)}</td>
    <td>
      {error && <p className="field-error" role="alert">{error.message}</p>}
      {!rejecting
        ? <div className="proposal-actions"><button type="button" className="button button-primary" disabled={busy || readOnly} onClick={() => void confirmar()}>Confirmar</button><button type="button" className="button button-secondary" disabled={busy || readOnly} onClick={() => setRejecting(true)}>Rechazar</button></div>
        : <div className="proposal-reject"><label htmlFor={`motivo-${item.documento_id}`}>Motivo del rechazo</label><input id={`motivo-${item.documento_id}`} value={motivo} onChange={event => setMotivo(event.target.value)} disabled={busy || readOnly} required /><div className="proposal-actions"><button type="button" className="button button-primary" disabled={busy || readOnly || !motivo.trim()} onClick={() => void rechazar()}>Confirmar rechazo</button><button type="button" className="button button-secondary" disabled={busy} onClick={() => setRejecting(false)}>Cancelar</button></div></div>}
    </td>
  </tr>;
}

export function PropuestasScreen({ accessOverride, readOnly = false }: { accessOverride?: PropuestasAccess; readOnly?: boolean } = {}) {
  const access = accessOverride ?? propuestasAccess();
  const [offset, setOffset] = useState(0);
  const [refreshToken, setRefreshToken] = useState(0);
  const bandeja = usePrototypeRead(() => access.readPropuestasPendientes({ offset, limit: PAGE_SIZE }), [access, offset, refreshToken]);
  function onChanged() { setRefreshToken(token => token + 1); }
  return <>
    {readOnly && <div className="availability-warning" role="note"><strong>Vista de diseño no interactiva</strong><span>Los botones están deshabilitados y no ejecutan comandos reales.</span></div>}
    {bandeja.loading ? <LoadingState /> : bandeja.error ? <ErrorState message={bandeja.error.message} requestId={bandeja.error instanceof ApiFailure && bandeja.error.detail.referenceSource === 'server' ? bandeja.error.detail.requestId : undefined} /> : <>
      <div className="projection-table-wrap"><table className="projection-table"><thead><tr><th>Sujeto / origen</th><th>Requisito</th><th>Vigencia propuesta</th><th>Propuesto el</th><th>Acción</th></tr></thead><tbody>
        {bandeja.data?.items.map(item => <ProposalRow key={item.documento_id} item={item} onChanged={onChanged} access={access} readOnly={readOnly} />)}
      </tbody></table></div>
      {bandeja.data?.items.length === 0 && <p className="empty-inline">Sin propuestas pendientes de revisión.</p>}
      {bandeja.data && <PaginationControls offset={bandeja.data.offset} limit={bandeja.data.limit} total={bandeja.data.total} onOffsetChange={setOffset} />}
    </>}
  </>;
}

