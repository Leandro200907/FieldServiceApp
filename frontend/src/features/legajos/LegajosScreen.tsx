import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { deriveVisualState } from '../documentation-planning/contracts';
import type { VisualCalendarState } from '../documentation-planning/contracts';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isLegajosIntegrated, legajosAccess } from './access';
import type { EvidenciaVigente, SubjectKind } from './contracts';
import '../documentation-planning/planning.css';
import '../mi-legajo/mi-legajo.css';

const visualStateLabels: Record<VisualCalendarState, string> = { verificada: 'Verificada', vencida: 'Vencida', declarada: 'Declarada' };
const tipoLabels: Record<string, string> = { persona: 'Persona', vehiculo: 'Vehículo', equipo: 'Equipo', empresa: 'Empresa' };
const TIPO_OPTIONS: SubjectKind[] = ['persona', 'vehiculo', 'equipo', 'empresa'];

function EvidenceRow({ item }: { item: EvidenciaVigente }) {
  const state = deriveVisualState(item);
  return <li className="evidence-row">
    <span className="evidence-name">{item.requisito || 'Requisito sin nombre'}</span>
    <Badge tone={state === 'vencida' ? 'warning' : 'accent'}>{visualStateLabels[state]}</Badge>
    <small>{item.vigente_hasta} · {item.dias_para_vencer >= 0 ? `vence en ${item.dias_para_vencer} días` : `venció hace ${Math.abs(item.dias_para_vencer)} días`}</small>
  </li>;
}

export function LegajosScreen() {
  const [q, setQ] = useState('');
  const [tipoSujeto, setTipoSujeto] = useState<SubjectKind | ''>('');
  const [selected, setSelected] = useState<string | null>(null);
  const search = usePrototypeRead(() => legajosAccess().searchSujetos({ q: q || undefined, tipoSujeto: tipoSujeto || undefined, limit: 20 }), [q, tipoSujeto]);
  const legajo = usePrototypeRead(() => selected ? legajosAccess().readLegajo(selected) : Promise.resolve(null), [selected]);
  const integrated = isLegajosIntegrated();
  return <>
    {integrated
      ? <div className="prototype-banner"><Badge tone="accent">Conectado al backend</Badge><div><strong>Legajos en tu alcance</strong><p>Buscá un sujeto para ver su documentación.</p></div></div>
      : <div className="prototype-banner"><Badge tone="warning">Mock contractual temporal</Badge><div><strong>Diseño no integrado</strong><p>Sujetos y documentación son ejemplos temporales. El contrato de forma ya es el real; el dato todavía no viene del backend.</p></div></div>}
    <section className="panel">
      <div className="form-grid">
        <div className="form-field"><label htmlFor="legajo-search">Buscar sujeto</label><input id="legajo-search" type="search" value={q} onChange={event => setQ(event.target.value)} placeholder="Nombre o identificador" /></div>
        <div className="form-field"><label htmlFor="legajo-tipo">Tipo</label><select id="legajo-tipo" value={tipoSujeto} onChange={event => setTipoSujeto(event.target.value as SubjectKind | '')}><option value="">Todos</option>{TIPO_OPTIONS.map(tipo => <option key={tipo} value={tipo}>{tipoLabels[tipo]}</option>)}</select></div>
      </div>
      {search.loading ? <LoadingState /> : search.error ? <ErrorState message={search.error.message} requestId={search.error instanceof ApiFailure && search.error.detail.referenceSource === 'server' ? search.error.detail.requestId : undefined} /> : <>
        <ul className="evidence-list">
          {search.data?.items.map(sujeto => <li key={sujeto.sujeto_id} className="evidence-row">
            <button type="button" className="text-button" onClick={() => setSelected(sujeto.sujeto_id)}>{sujeto.identificador_natural}</button>
            <Badge>{tipoLabels[sujeto.tipo_sujeto] || sujeto.tipo_sujeto}</Badge>
            <small>{sujeto.dado_de_baja_en ? 'Dado de baja' : 'Activo'}</small>
          </li>)}
        </ul>
        {search.data?.items.length === 0 && <p className="empty-inline">Sin sujetos que coincidan con la búsqueda.</p>}
      </>}
    </section>
    {selected && (legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} requestId={legajo.error instanceof ApiFailure && legajo.error.detail.referenceSource === 'server' ? legajo.error.detail.requestId : undefined} /> : legajo.data && <section className="panel resource-panel">
      <div className="panel-top"><span className="section-number">{tipoLabels[legajo.data.legajo.tipo_sujeto] || legajo.data.legajo.tipo_sujeto}</span><Badge tone={legajo.data.resumen.vencidos > 0 ? 'warning' : 'accent'}>{legajo.data.resumen.vencidos > 0 ? `${legajo.data.resumen.vencidos} vencido${legajo.data.resumen.vencidos > 1 ? 's' : ''}` : 'Todo vigente'}</Badge></div>
      <h3>{legajo.data.legajo.identificador_natural}</h3>
      <p className="muted">Hoy: {legajo.data.hoy} · {legajo.data.legajo.dado_de_baja_en ? 'Dado de baja' : 'Activo'}</p>
      {[...legajo.data.documentos, ...legajo.data.acreditaciones, ...legajo.data.inducciones].length === 0
        ? <p className="empty-inline">Sin documentación registrada.</p>
        : <ul className="evidence-list">{[...legajo.data.documentos, ...legajo.data.acreditaciones, ...legajo.data.inducciones].map(item => <EvidenceRow key={item.id} item={item} />)}</ul>}
    </section>)}
  </>;
}
