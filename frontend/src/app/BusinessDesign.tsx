import { ReadViewDesign } from './ReadViewDesign';
import type { Page } from './capabilities';
import { BlockedSelector } from '../ui/States';
import { CalendarDocumentalScreen } from '../features/documentation-planning/CalendarDocumentalScreen';
import { RadarDocumentalScreen } from '../features/documentation-planning/RadarDocumentalScreen';
import { MiLegajoScreen } from '../features/mi-legajo/MiLegajoScreen';
import { VencimientosScreen } from '../features/vencimientos/VencimientosScreen';
import { LegajosScreen } from '../features/legajos/LegajosScreen';
import { PropuestasScreen } from '../features/propuestas/PropuestasScreen';
import type { PropuestasAccess } from '../features/propuestas/contracts';
import { AuditoriaScreen } from '../features/auditoria/AuditoriaScreen';
import { MatricesScreen } from '../features/matrices/MatricesScreen';

const selectors: Partial<Record<Page['id'], Array<[string, string]>>> = {
  configuracion: [['Definición local', 'SEL-13 · catálogo existente; integración pendiente']],
};
export function BusinessDesign({ page, technicalNotes = false, roles = [], propuestasDeDiseno, propuestasSoloLectura = false }: { page: Page; technicalNotes?: boolean; roles?: readonly string[]; propuestasDeDiseno?: PropuestasAccess; propuestasSoloLectura?: boolean }) {
  if (page.id === 'calendario-vigencias') return <><CalendarDocumentalScreen roles={roles} />{technicalNotes && <p className="technical-note">Q-DOC-01 · GET /v1/consultas/calendario_vigencias implementado y con adaptador real (`realDocumentationPlanningAccess`); activación detrás de `featureFlags.documentationCalendarIntegration` (hoy `false`). Q-DOC-03 (GET /v1/consultas/detalle_proyeccion_documental, detalle de tramo por referencia) también implementado en el backend — el frontend todavía no lo consume desde esta pantalla (F-08).</p>}</>;
  if (page.id === 'radar-documental') return <><RadarDocumentalScreen roles={roles} />{technicalNotes && <p className="technical-note">GET /v1/consultas/radar_documental_backlog, radar_documental_oc y detalle por legajo integrados. La consulta es informativa y no asigna recursos.</p>}</>;
  if (page.id === 'mi-legajo') return <><MiLegajoScreen />{technicalNotes && <p className="technical-note">GET /v1/consultas/mi_legajo integrado. La pantalla presenta únicamente el legajo personal; las custodias y asignaciones de recursos quedan fuera del Módulo 1 visible.</p>}</>;
  if (page.id === 'vencimientos') return <><VencimientosScreen />{technicalNotes && <p className="technical-note">G-01 / H-02 · GET /v1/consultas/tablero_vencimientos implementado, tipado y con adaptador real (`realVencimientosAccess`); activación detrás de `featureFlags.expirationsBoardIntegration` (hoy `false`). Muestra solo la consulta de vencimientos — el ciclo de alertas (agregado persistente, políticas, recordatorio, escalamiento) sigue detrás de `alertConfiguration`/`alertLifecycle`, capacidad distinta y no implementada.</p>}</>;
  if (page.id === 'legajos') return <><LegajosScreen />{technicalNotes && <p className="technical-note">SEL-01 · GET /v1/consultas/sujetos (búsqueda) y GET /v1/consultas/legajo (detalle por sujeto_id) implementados y con adaptador real (`realLegajosAccess`); activación detrás de `featureFlags.legajoLookupIntegration` (hoy `false`). El sujeto elegido siempre sale de una búsqueda ya acotada al alcance del usuario, nunca de un id libre.</p>}</>;
  if (page.id === 'propuestas') return <><PropuestasScreen accessOverride={propuestasDeDiseno} readOnly={propuestasSoloLectura} />{technicalNotes && <p className="technical-note">Vista de diseño aislada con datos sintéticos y comandos deshabilitados. La pantalla operativa real integra propuestas fuera de este catálogo.</p>}</>;
  if (page.id === 'auditoria') return <><AuditoriaScreen />{technicalNotes && <p className="technical-note">GET /v1/consultas/log_auditoria implementado y con adaptador real (`realAuditoriaAccess`); activación detrás de `featureFlags.auditLogIntegration` (hoy `false`). El payload de cada evento se muestra tal cual lo entrega el servidor, sin interpretarlo del lado del cliente.</p>}</>;
  if (page.id === 'matrices') return <><MatricesScreen />{technicalNotes && <p className="technical-note">SEL-12 · GET /v1/consultas/matrices y GET /v1/consultas/matriz_vigente implementados y con adaptador real (`realMatricesAccess`); activación detrás de `featureFlags.matricesIntegration` (hoy `false`). SEL-09/10/11 siguen abiertos: no existe catálogo de nombres para cliente/locación/tipo de servicio, se muestran los IDs crudos.</p>}</>;
  const fields = (selectors[page.id] || []).filter(([label]) => !label.includes('Responsable') || roles.includes('responsable_legajos'));
  return <><ReadViewDesign key={page.id} pageId={page.id} technicalNotes={technicalNotes} />{fields.length > 0 && <section className="panel"><h3>Selección de contexto</h3><div className="form-grid">{fields.map(([label, dependency]) => <BlockedSelector key={label} label={label} dependency={dependency} />)}</div></section>}
    {technicalNotes && <p className="technical-note">Dependencias: {page.gaps.join(' · ')}. No se ejecutan consultas de negocio desde esta lámina.</p>}
  </>;
}

