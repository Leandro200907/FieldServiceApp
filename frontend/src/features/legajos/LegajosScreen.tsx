import { useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { EvidenciaRow } from '../../ui/EvidenciaRow';
import { subtituloLegajoPersona, tituloLegajoPersona } from './legajoDisplay';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { isLegajosIntegrated, legajosAccess } from './access';
import type { SubjectKind } from './contracts';
import '../documentation-planning/planning.css';
import '../mi-legajo/mi-legajo.css';

const tipoLabels: Record<string, string> = { persona: 'Persona', vehiculo: 'Vehículo', equipo: 'Equipo', empresa: 'Empresa' };
const TIPO_OPTIONS: SubjectKind[] = ['persona', 'vehiculo', 'equipo', 'empresa'];

export function LegajosScreen() {
  const [q, setQ] = useState('');
  const [tipoSujeto, setTipoSujeto] = useState<SubjectKind | ''>('');
  const [selected, setSelected] = useState<string | null>(null);
  const search = usePrototypeRead(() => legajosAccess().searchSujetos({ q: q || undefined, tipoSujeto: tipoSujeto || undefined, limit: 20 }), [q, tipoSujeto]);
  const legajo = usePrototypeRead(() => selected ? legajosAccess().readLegajo(selected) : Promise.resolve(null), [selected]);
  const espejoOperadora = usePrototypeRead(() => selected ? legajosAccess().readEspejoOperadora(selected) : Promise.resolve(null), [selected]);
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
            <button type="button" className="text-button" onClick={() => setSelected(sujeto.sujeto_id)}>
              {tituloLegajoPersona(sujeto)}
              {subtituloLegajoPersona(sujeto) && <small> · {subtituloLegajoPersona(sujeto)}</small>}
            </button>
            <Badge>{tipoLabels[sujeto.tipo_sujeto] || sujeto.tipo_sujeto}</Badge>
            <small>{sujeto.dado_de_baja_en ? 'Dado de baja' : 'Activo'}</small>
          </li>)}
        </ul>
        {search.data?.items.length === 0 && <p className="empty-inline">Sin sujetos que coincidan con la búsqueda.</p>}
      </>}
    </section>
    {selected && (legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} requestId={legajo.error instanceof ApiFailure && legajo.error.detail.referenceSource === 'server' ? legajo.error.detail.requestId : undefined} /> : legajo.data && <section className="panel resource-panel">
      <div className="panel-top"><span className="section-number">{tipoLabels[legajo.data.legajo.tipo_sujeto] || legajo.data.legajo.tipo_sujeto}</span><Badge tone={legajo.data.resumen.vencidos > 0 ? 'warning' : 'accent'}>{legajo.data.resumen.vencidos > 0 ? `${legajo.data.resumen.vencidos} vencido${legajo.data.resumen.vencidos > 1 ? 's' : ''}` : 'Todo vigente'}</Badge></div>
      <h3>{tituloLegajoPersona(legajo.data.legajo)}</h3>
      {subtituloLegajoPersona(legajo.data.legajo) && <p className="muted">{subtituloLegajoPersona(legajo.data.legajo)}</p>}
      <p className="muted">Hoy: {legajo.data.hoy} · {legajo.data.legajo.dado_de_baja_en ? 'Dado de baja' : 'Activo'}</p>
      {[...legajo.data.documentos, ...legajo.data.acreditaciones, ...legajo.data.inducciones].length === 0
        ? <p className="empty-inline">Sin documentación registrada.</p>
        : <ul className="evidence-list">{[...legajo.data.documentos, ...legajo.data.acreditaciones, ...legajo.data.inducciones].map(item => <EvidenciaRow key={item.id} item={item} hoyIso={legajo.data!.hoy} />)}</ul>}
    </section>)}
    {selected && (espejoOperadora.loading ? <LoadingState /> : espejoOperadora.error ? <ErrorState message={espejoOperadora.error.message} requestId={espejoOperadora.error instanceof ApiFailure && espejoOperadora.error.detail.referenceSource === 'server' ? espejoOperadora.error.detail.requestId : undefined} /> : espejoOperadora.data && (() => {
      const items = espejoOperadora.data.items;
      const sinPresentaciones = (espejoOperadora.data.total ?? 0) === 0;
      const conDiferencias = items.some(item => item.estado_operadora !== 'al_dia');
      const badgeLabel = sinPresentaciones ? 'Sin presentaciones registradas' : conDiferencias ? 'Con diferencias' : 'Al día';
      const badgeTone = sinPresentaciones ? 'accent' : conDiferencias ? 'warning' : 'accent';
      const estadoLabels: Record<string, string> = {
        pendiente_envio: 'Pendiente de envío',
        pendiente_aceptacion: 'Pendiente de aceptación',
        rechazado: 'Rechazado',
        al_dia: 'Al día',
      };
      return <section className="panel">
      <div className="panel-top"><div><p className="eyebrow">Espejo por operadora</p><h3>Estado externo del legajo</h3></div><Badge tone={badgeTone}>{badgeLabel}</Badge></div>
      {items.length ? <ul className="evidence-list">{items.map(item => <li className="evidence-row" key={`${item.operadora_id}-${item.requisito_definicion_id}-${item.sujeto_id}`}>
        <span className="evidence-name">{item.requisito} · {item.operadora}</span>
        <Badge tone={item.estado_operadora === 'al_dia' ? 'accent' : 'warning'}>{estadoLabels[item.estado_operadora as string] || item.estado_operadora}</Badge>
        <small>{item.motivo || '—'}</small>
      </li>)}</ul> : <p className="empty-inline">Sin filas en el espejo para este sujeto.</p>}
    </section>;
    })())}
  </>;
}

