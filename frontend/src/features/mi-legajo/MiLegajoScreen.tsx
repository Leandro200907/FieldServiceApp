import { useState } from 'react';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { RenovarDocumentoForm } from './RenovarDocumentoForm';
import { IncorporarDocumentoForm } from './IncorporarDocumentoForm';
import { textoCumplimientoExigidos } from '../legajos/legajoCumplimiento';
import { EvidenciaRow } from '../../ui/EvidenciaRow';
import { subtituloLegajoPersona, tituloLegajoPersona } from '../legajos/legajoDisplay';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { miLegajoAccess } from './access';
import type { EvidenciaVigente, LegajoCompuesto, ResumenLegajo } from './contracts';
import { ApiFailure, session } from '../../api';
import { formatFecha } from '../../ui/fechas';
import './mi-legajo.css';

function LegajoCard({ title, legajoNombre, sujetoId, documentos, acreditaciones, inducciones, resumen, hoyIso, renovarId, incorporarId, onRenovar, onIncorporar, onRenovado }: {
  title: string; legajoNombre: string; sujetoId: string;
  documentos: EvidenciaVigente[]; acreditaciones: EvidenciaVigente[]; inducciones: EvidenciaVigente[];
  resumen: ResumenLegajo;
  hoyIso: string;
  renovarId: string | null;
  incorporarId: string | null;
  onRenovar: (id: string) => void;
  onIncorporar: (id: string) => void;
  onRenovado: () => void;
}) {
  const items = [...documentos, ...acreditaciones, ...inducciones];
  const cumplimiento = (resumen.exigidos ?? 0) > 0
    ? `${resumen.en_regla_exigidos ?? 0} de ${resumen.exigidos} en regla (exigidos por OC)`
    : null;
  return <section className="panel resource-panel">
    <div className="panel-top"><Badge tone={(resumen.exigidos_vencidos ?? resumen.vencidos) > 0 ? 'warning' : 'accent'}>{cumplimiento || (resumen.vencidos > 0 ? `${resumen.vencidos} vencido${resumen.vencidos > 1 ? 's' : ''}` : 'Todo vigente')}</Badge></div>
    <h3 className="mi-legajo-card-title">{title}</h3>
    <p className="muted">{legajoNombre}</p>
    {items.length === 0
      ? <p className="empty-inline">Sin documentación registrada.</p>
      : <ul className="evidence-list">{items.map(item => (
        <li key={item.id} className="evidence-list-item">
          <EvidenciaRow item={item} hoyIso={hoyIso} onRenovar={() => onRenovar(item.id)} onIncorporar={() => onIncorporar(item.id)} />
          {renovarId === item.id && (
            <RenovarDocumentoForm item={item} sujetoId={sujetoId} hoyIso={hoyIso} onDone={onRenovado} onCancel={() => onRenovar('')} />
          )}
          {incorporarId === item.id && (
            <IncorporarDocumentoForm item={item} sujetoId={sujetoId} hoyIso={hoyIso} onDone={onRenovado} onCancel={() => onIncorporar('')} />
          )}
        </li>
      ))}</ul>}
  </section>;
}

export function MiLegajoScreen() {
  const [renovarId, setRenovarId] = useState<string | null>(null);
  const [incorporarId, setIncorporarId] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const legajo = usePrototypeRead(() => miLegajoAccess().readMiLegajo(), [refresh]);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  return <>
    {legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} requestId={legajo.error instanceof ApiFailure && legajo.error.detail.referenceSource === 'server' ? legajo.error.detail.requestId : undefined} /> : legajo.data && <>
      <div className="availability-warning" role="note"><strong>Hoy: {formatFecha(legajo.data.hoy, tz)}</strong><span>{textoCumplimientoExigidos(legajo.data.persona)} · cargados: {legajo.data.resumen.vencidos} vencido{legajo.data.resumen.vencidos === 1 ? '' : 's'}.</span></div>
      <div className="composite-grid">
        <LegajoCard title="Mi documentación" legajoNombre={[tituloLegajoPersona(legajo.data.persona.legajo), subtituloLegajoPersona(legajo.data.persona.legajo)].filter(Boolean).join(' · ')}
          sujetoId={legajo.data.persona.legajo.sujeto_id}
          documentos={legajo.data.persona.documentos} acreditaciones={legajo.data.persona.acreditaciones} inducciones={legajo.data.persona.inducciones}
          resumen={legajo.data.persona.resumen} hoyIso={legajo.data.hoy}
          renovarId={renovarId} incorporarId={incorporarId}
          onRenovar={id => { setRenovarId(id || null); if (id) setIncorporarId(null); }}
          onIncorporar={id => { setIncorporarId(id || null); if (id) setRenovarId(null); }}
          onRenovado={() => { setRenovarId(null); setIncorporarId(null); setRefresh(t => t + 1); }} />
      </div>
    </>}
  </>;
}


