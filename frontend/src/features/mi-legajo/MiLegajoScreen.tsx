import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { deriveVisualState } from '../documentation-planning/contracts';
import type { VisualCalendarState } from '../documentation-planning/contracts';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isMiLegajoIntegrated, miLegajoAccess } from './access';
import type { EvidenciaVigente, LegajoCompuesto, RecursoCustodiado } from './contracts';
import { ApiFailure } from '../../api';
import './mi-legajo.css';

const visualStateLabels: Record<VisualCalendarState, string> = { verificada: 'Verificada', vencida: 'Vencida', declarada: 'Declarada' };
const tipoRecursoLabels: Record<string, string> = { vehiculo: 'Vehículo', equipo: 'Equipo' };

function EvidenceRow({ item }: { item: EvidenciaVigente }) {
  const state = deriveVisualState(item);
  return <li className="evidence-row">
    <span className="evidence-name">{item.requisito || 'Requisito sin nombre'}</span>
    <Badge tone={state === 'vencida' ? 'warning' : 'accent'}>{visualStateLabels[state]}</Badge>
    <small>{item.vigente_hasta} · {item.dias_para_vencer >= 0 ? `vence en ${item.dias_para_vencer} días` : `venció hace ${Math.abs(item.dias_para_vencer)} días`}</small>
  </li>;
}

function LegajoCard({ title, number, legajoNombre, documentos, acreditaciones, inducciones, resumen }: {
  title: string; number: string; legajoNombre: string;
  documentos: EvidenciaVigente[]; acreditaciones: EvidenciaVigente[]; inducciones: EvidenciaVigente[];
  resumen: { total: number; vigentes_hoy: number; vencidos: number };
}) {
  const items = [...documentos, ...acreditaciones, ...inducciones];
  return <section className="panel resource-panel">
    <div className="panel-top"><span className="section-number">{number}</span><Badge tone={resumen.vencidos > 0 ? 'warning' : 'accent'}>{resumen.vencidos > 0 ? `${resumen.vencidos} vencido${resumen.vencidos > 1 ? 's' : ''}` : 'Todo vigente'}</Badge></div>
    <h3>{title}</h3>
    <p className="muted">{legajoNombre}</p>
    {items.length === 0
      ? <p className="empty-inline">Sin documentación registrada.</p>
      : <ul className="evidence-list">{items.map(item => <EvidenceRow key={item.id} item={item} />)}</ul>}
  </section>;
}

export function MiLegajoScreen() {
  const legajo = usePrototypeRead(() => miLegajoAccess().readMiLegajo(), []);
  const integrated = isMiLegajoIntegrated();
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Tu legajo compuesto</strong><p>Tu persona y los vehículos/equipos bajo tu custodia vigente hoy.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Documentos y vigencias son ejemplos temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    {legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} requestId={legajo.error instanceof ApiFailure && legajo.error.detail.referenceSource === 'server' ? legajo.error.detail.requestId : undefined} /> : legajo.data && <>
      <div className="availability-warning" role="note"><strong>Hoy: {legajo.data.hoy}</strong><span>{legajo.data.resumen.vencidos} vencido{legajo.data.resumen.vencidos === 1 ? '' : 's'} · {legajo.data.resumen.vigentes_hoy} vigente{legajo.data.resumen.vigentes_hoy === 1 ? '' : 's'} hoy, entre tu persona y tus recursos bajo custodia.</span></div>
      <div className="composite-grid">
        <LegajoCard title="Persona" number="01" legajoNombre={(legajo.data.persona as LegajoCompuesto).legajo.identificador_natural}
          documentos={legajo.data.persona.documentos} acreditaciones={legajo.data.persona.acreditaciones} inducciones={legajo.data.persona.inducciones}
          resumen={legajo.data.persona.resumen} />
        {legajo.data.recursos_bajo_custodia.map((recurso: RecursoCustodiado, index: number) => <LegajoCard key={recurso.periodo_id}
          title={tipoRecursoLabels[recurso.tipo_recurso] || recurso.tipo_recurso} number={String(index + 2).padStart(2, '0')}
          legajoNombre={`${recurso.legajo.identificador_natural} · bajo tu custodia desde ${recurso.custodia_desde}`}
          documentos={recurso.documentos} acreditaciones={recurso.acreditaciones} inducciones={recurso.inducciones}
          resumen={recurso.resumen} />)}
        {legajo.data.recursos_bajo_custodia.length === 0 && <section className="panel resource-panel"><div className="panel-top"><span className="section-number">02</span></div><h3>Sin recursos bajo custodia</h3><p className="muted">No tenés vehículos ni equipos asignados hoy.</p></section>}
      </div>
    </>}
    <section className="module-boundary"><strong>Límite con Módulo 2</strong><span>Sin arrastrar ni asignar recursos</span><span>Sin modificar fechas</span><span>Sin crear OT</span><span>Sin ejecución, tiempos reales, firma ni certificados</span></section>
  </>;
}
