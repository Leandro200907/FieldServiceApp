import { useState } from 'react';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { RenovarDocumentoForm } from './RenovarDocumentoForm';
import { EvidenciaRow } from '../../ui/EvidenciaRow';
import { subtituloLegajoPersona, tituloLegajoPersona } from '../legajos/legajoDisplay';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { miLegajoAccess } from './access';
import type { EvidenciaVigente, LegajoCompuesto } from './contracts';
import { ApiFailure, session } from '../../api';
import { formatFecha } from '../../ui/fechas';
import './mi-legajo.css';

function LegajoCard({ title, legajoNombre, sujetoId, documentos, acreditaciones, inducciones, resumen, hoyIso, renovarId, onRenovar, onRenovado }: {
  title: string; legajoNombre: string; sujetoId: string;
  documentos: EvidenciaVigente[]; acreditaciones: EvidenciaVigente[]; inducciones: EvidenciaVigente[];
  resumen: { total: number; vigentes_hoy: number; por_vencer?: number; vencidos: number };
  hoyIso: string;
  renovarId: string | null;
  onRenovar: (id: string) => void;
  onRenovado: () => void;
}) {
  const items = [...documentos, ...acreditaciones, ...inducciones];
  const renovarItem = renovarId ? items.find(i => i.id === renovarId) : null;
  return <section className="panel resource-panel">
    <div className="panel-top"><Badge tone={resumen.vencidos > 0 ? 'warning' : 'accent'}>{resumen.vencidos > 0 ? `${resumen.vencidos} vencido${resumen.vencidos > 1 ? 's' : ''}` : 'Todo vigente'}</Badge></div>
    <h3 className="mi-legajo-card-title">{title}</h3>
    <p className="muted">{legajoNombre}</p>
    {items.length === 0
      ? <p className="empty-inline">Sin documentación registrada.</p>
      : <ul className="evidence-list">{items.map(item => <EvidenciaRow key={item.id} item={item} hoyIso={hoyIso} onRenovar={() => onRenovar(item.id)} />)}</ul>}
    {renovarItem && <RenovarDocumentoForm item={renovarItem} sujetoId={sujetoId} hoyIso={hoyIso} onDone={onRenovado} onCancel={() => onRenovar('')} />}
  </section>;
}

export function MiLegajoScreen() {
  const [renovarId, setRenovarId] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const legajo = usePrototypeRead(() => miLegajoAccess().readMiLegajo(), [refresh]);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  return <>
    {legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} requestId={legajo.error instanceof ApiFailure && legajo.error.detail.referenceSource === 'server' ? legajo.error.detail.requestId : undefined} /> : legajo.data && <>
      <div className="availability-warning" role="note"><strong>Hoy: {formatFecha(legajo.data.hoy, tz)}</strong><span>{legajo.data.resumen.vencidos} vencido{legajo.data.resumen.vencidos === 1 ? '' : 's'} · {(legajo.data.resumen.por_vencer ?? 0)} por vencer · {legajo.data.resumen.vigentes_hoy} vigente{legajo.data.resumen.vigentes_hoy === 1 ? '' : 's'} en tu legajo personal.</span></div>
      <div className="composite-grid">
        <LegajoCard title="Mi documentación" legajoNombre={[tituloLegajoPersona(legajo.data.persona.legajo), subtituloLegajoPersona(legajo.data.persona.legajo)].filter(Boolean).join(' · ')}
          sujetoId={legajo.data.persona.legajo.sujeto_id}
          documentos={legajo.data.persona.documentos} acreditaciones={legajo.data.persona.acreditaciones} inducciones={legajo.data.persona.inducciones}
          resumen={legajo.data.persona.resumen} hoyIso={legajo.data.hoy}
          renovarId={renovarId} onRenovar={id => setRenovarId(id || null)} onRenovado={() => { setRenovarId(null); setRefresh(t => t + 1); }} />
      </div>
    </>}
  </>;
}


