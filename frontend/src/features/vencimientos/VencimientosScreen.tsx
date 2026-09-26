import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { deriveVisualState } from '../documentation-planning/contracts';
import type { VisualCalendarState } from '../documentation-planning/contracts';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isVencimientosIntegrated, vencimientosAccess } from './access';
import '../documentation-planning/planning.css';

const visualStateLabels: Record<VisualCalendarState, string> = { verificada: 'Verificada', vencida: 'Vencida', declarada: 'Declarada' };
const DIAS_OPTIONS = [7, 15, 30, 60, 90];

export function VencimientosScreen() {
  const [dias, setDias] = useState(30);
  const [offset, setOffset] = useState(0);
  const tablero = usePrototypeRead(() => vencimientosAccess().readTableroVencimientos({ dias, offset, limit: PAGE_SIZE }), [dias, offset]);
  const integrated = isVencimientosIntegrated();
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Tablero de vencimientos</strong><p>Evidencia vigente que vence dentro de la ventana elegida, o ya vencida.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Ítems de ejemplo temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    <div className="availability-warning" role="note"><strong>Solo consulta de vencimientos</strong><span>Sin agregado, políticas, recordatorios ni escalamiento — eso es el ciclo de alertas (H-02), una capacidad distinta.</span></div>
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
            <td>{item.dias_para_vencer >= 0 ? `vence en ${item.dias_para_vencer} días` : `venció hace ${Math.abs(item.dias_para_vencer)} días`}</td>
          </tr>;
        })}
      </tbody></table></div>
      {tablero.data?.items.length === 0 && <p className="empty-inline">Sin vencimientos en esta ventana y alcance.</p>}
      {tablero.data && <PaginationControls offset={tablero.data.offset} limit={tablero.data.limit} total={tablero.data.total} onOffsetChange={setOffset} />}
    </>}
  </>;
}
