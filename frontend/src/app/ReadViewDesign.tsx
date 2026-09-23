import { useState } from 'react';
import type { PageId } from './capabilities';
import { Badge, EmptyState, ErrorState, LoadingState, Pending } from '../ui/States';

type PreviewState = 'pending' | 'loading' | 'empty' | 'error';
const views: Partial<Record<PageId, { title: string; columns: string[]; endpoint: string; note: string }>> = {
  matrices: { title: 'Matrices documentales', columns: ['Cliente', 'Locación', 'Servicio', 'Versión', 'Vigencia'], endpoint: '/v1/consultas/matrices', note: 'Las reglas de obligatoriedad se resuelven en el backend según matriz y contexto de OC.' },
  oc: { title: 'Backlog de órdenes de compra', columns: ['OC', 'Período previsto', 'Estado', 'Última decisión visible'], endpoint: '/v1/consultas/backlog_oc', note: 'Una decisión documental no garantiza disponibilidad ni asignación operativa.' },
  auditoria: { title: 'Eventos registrados', columns: ['Fecha', 'Actor', 'Evento', 'Referencia'], endpoint: '/v1/consultas/log_auditoria', note: 'Consulta de trazabilidad. Los eventos se presentan como los entrega el servidor.' },
};

/** Presentation only: never issues requests or manufactures business records. */
export function ReadViewDesign({ pageId, technicalNotes }: { pageId: PageId; technicalNotes: boolean }) {
  const [state, setState] = useState<PreviewState>('pending');
  const view = views[pageId];
  if (!view) return null;
  return <section className="panel read-view-design" aria-label={view.title}>
    <div className="panel-top"><h3>{view.title}</h3><Badge tone="warning">Diseño · sin conexión</Badge></div>
    <p>{view.note}</p>
    {technicalNotes && <div className="preview-state-controls"><label htmlFor={`preview-${pageId}`}>Estado de presentación</label><select id={`preview-${pageId}`} value={state} onChange={e => setState(e.target.value as PreviewState)}><option value="pending">Pendiente de integración</option><option value="loading">Ejemplo: cargando</option><option value="empty">Ejemplo: respuesta vacía</option><option value="error">Ejemplo: error</option></select><small>Vista de diseño. No representa una respuesta del servidor.</small></div>}
    <div className="read-table-scroll" role="region" aria-label={`Estructura de ${view.title}`} tabIndex={0}><table className="read-table"><caption>Campos previstos · sin registros de negocio</caption><thead><tr>{view.columns.map(column => <th scope="col" key={column}>{column}</th>)}</tr></thead><tbody><tr><td colSpan={view.columns.length}>
      {state === 'pending' && <Pending title="Datos pendientes de integración">Todavía no consultamos esta información. No se muestra un total ni se presume que la lista esté vacía.</Pending>}
      {state === 'loading' && <LoadingState />}
      {state === 'empty' && <EmptyState />}
      {state === 'error' && <ErrorState message="Ejemplo de conexión interrumpida. No se envió una solicitud." requestId="EJEMPLO-NO-REAL" onRetry={() => setState('loading')} />}
    </td></tr></tbody></table></div>
    {technicalNotes && <p className="technical-note">Consulta existente en el contrato candidato db400e6: <code>{view.endpoint}</code>. Su existencia no implica integración validada.</p>}
  </section>;
}
