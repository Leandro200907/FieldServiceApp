import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { EvidenciaRow } from '../../ui/EvidenciaRow';
import { subtituloLegajoPersona, tituloLegajoPersona } from '../legajos/legajoDisplay';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isMiLegajoIntegrated, miLegajoAccess } from './access';
import type { EvidenciaVigente, LegajoCompuesto } from './contracts';
import { ApiFailure } from '../../api';
import './mi-legajo.css';

function LegajoCard({ title, number, legajoNombre, documentos, acreditaciones, inducciones, resumen }: {
  title: string; number: string; legajoNombre: string;
  documentos: EvidenciaVigente[]; acreditaciones: EvidenciaVigente[]; inducciones: EvidenciaVigente[];
  resumen: { total: number; vigentes_hoy: number; por_vencer?: number; vencidos: number };
}) {
  const items = [...documentos, ...acreditaciones, ...inducciones];
  return <section className="panel resource-panel">
    <div className="panel-top"><span className="section-number">{number}</span><Badge tone={resumen.vencidos > 0 ? 'warning' : 'accent'}>{resumen.vencidos > 0 ? `${resumen.vencidos} vencido${resumen.vencidos > 1 ? 's' : ''}` : 'Todo vigente'}</Badge></div>
    <h3>{title}</h3>
    <p className="muted">{legajoNombre}</p>
    {items.length === 0
      ? <p className="empty-inline">Sin documentación registrada.</p>
      : <ul className="evidence-list">{items.map(item => <EvidenciaRow key={item.id} item={item} />)}</ul>}
  </section>;
}

export function MiLegajoScreen() {
  const legajo = usePrototypeRead(() => miLegajoAccess().readMiLegajo(), []);
  const integrated = isMiLegajoIntegrated();
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Tu legajo documental</strong><p>Documentación registrada para tu persona.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Documentos y vigencias son ejemplos temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    {legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} requestId={legajo.error instanceof ApiFailure && legajo.error.detail.referenceSource === 'server' ? legajo.error.detail.requestId : undefined} /> : legajo.data && <>
      <div className="availability-warning" role="note"><strong>Hoy: {legajo.data.hoy}</strong><span>{legajo.data.resumen.vencidos} vencido{legajo.data.resumen.vencidos === 1 ? '' : 's'} · {(legajo.data.resumen.por_vencer ?? 0)} por vencer · {legajo.data.resumen.vigentes_hoy} vigente{legajo.data.resumen.vigentes_hoy === 1 ? '' : 's'} en tu legajo personal.</span></div>
      <div className="composite-grid">
        <LegajoCard title="Persona" number="01" legajoNombre={[tituloLegajoPersona(legajo.data.persona.legajo), subtituloLegajoPersona(legajo.data.persona.legajo)].filter(Boolean).join(' · ')}
          documentos={legajo.data.persona.documentos} acreditaciones={legajo.data.persona.acreditaciones} inducciones={legajo.data.persona.inducciones}
          resumen={legajo.data.persona.resumen} />
      </div>
    </>}
    <section className="module-boundary"><strong>Límite con Módulo 2</strong><span>Sin custodias ni recursos asignados</span><span>Sin modificar fechas</span><span>Sin crear OT</span><span>Sin ejecución, tiempos reales, firma ni certificados</span></section>
  </>;
}


