import { ReadViewDesign } from './ReadViewDesign';
import type { Page } from './capabilities';
import { BlockedSelector } from '../ui/States';
import { CalendarDocumentalScreen } from '../features/documentation-planning/CalendarDocumentalScreen';
import { RadarDocumentalScreen } from '../features/documentation-planning/RadarDocumentalScreen';
import { BacklogOcScreen } from '../features/documentation-planning/BacklogOcScreen';
import { TimelineRecursosScreen } from '../features/documentation-planning/TimelineRecursosScreen';
import { AccionesPendientesScreen } from '../features/documentation-planning/AccionesPendientesScreen';
import { CatalogosOcScreen } from '../features/documentation-planning/CatalogosOcScreen';
import { MiLegajoScreen } from '../features/mi-legajo/MiLegajoScreen';
import { VencimientosScreen } from '../features/vencimientos/VencimientosScreen';
import { LegajosScreen } from '../features/legajos/LegajosScreen';
import { PropuestasScreen } from '../features/propuestas/PropuestasScreen';
import type { PropuestasAccess } from '../features/propuestas/contracts';
import { AuditoriaScreen } from '../features/auditoria/AuditoriaScreen';
import { MatricesScreen } from '../features/matrices/MatricesScreen';

const selectors: Partial<Record<Page['id'], Array<[string, string]>>> = {
  configuracion: [['Definición local', 'Catálogo local; integración pendiente']],
};
export function BusinessDesign({ page, technicalNotes = false, roles = [], propuestasDeDiseno, propuestasSoloLectura = false, detailId }: { page: Page; technicalNotes?: boolean; roles?: readonly string[]; propuestasDeDiseno?: PropuestasAccess; propuestasSoloLectura?: boolean; detailId?: string }) {
  if (page.id === 'calendario-vigencias') return <><CalendarDocumentalScreen roles={roles} />{technicalNotes && <p className="technical-note">Q-DOC-01 · GET /v1/consultas/calendario_vigencias implementado y con adaptador real (`realDocumentationPlanningAccess`); activación detrás de `featureFlags.documentationCalendarIntegration` (hoy `false`). Q-DOC-03 (GET /v1/consultas/detalle_proyeccion_documental, detalle de tramo por referencia) también implementado en el backend — el frontend todavía no lo consume desde esta pantalla (F-08).</p>}</>;
  if (page.id === 'radar-documental') return <><RadarDocumentalScreen roles={roles} detailId={detailId} />{technicalNotes && <p className="technical-note">GET /v1/consultas/radar_documental_backlog, radar_documental_oc y detalle por legajo integrados. La consulta es informativa y no asigna recursos.</p>}</>;
  if (page.id === 'backlog-oc') return <><BacklogOcScreen roles={roles} detailId={detailId} />{technicalNotes && <p className="technical-note">GET /v1/consultas/backlog_oc y cobertura_oc · modo consulta.</p>}</>;
  if (page.id === 'acciones-pendientes') return <><AccionesPendientesScreen />{technicalNotes && <p className="technical-note">GET /v1/consultas/acciones_pendientes</p>}</>;
  if (page.id === 'timeline-recursos') return <><TimelineRecursosScreen roles={roles} />{technicalNotes && <p className="technical-note">GET /v1/consultas/timeline_recursos</p>}</>;
  if (page.id === 'catalogos-oc') return <><CatalogosOcScreen />{technicalNotes && <p className="technical-note">GET /v1/consultas/catalogos_oc · altas por comando.</p>}</>;
  if (page.id === 'mi-legajo') return <><MiLegajoScreen />{technicalNotes && <p className="technical-note">GET /v1/consultas/mi_legajo integrado. La pantalla presenta únicamente el legajo personal; las custodias y asignaciones de recursos quedan fuera del Módulo 1 visible.</p>}</>;
  if (page.id === 'vencimientos') return <><VencimientosScreen />{technicalNotes && <p className="technical-note">G-01 / H-02 · GET /v1/consultas/tablero_vencimientos implementado, tipado y con adaptador real (`realVencimientosAccess`); activación detrás de `featureFlags.expirationsBoardIntegration` (hoy `false`). Muestra solo la consulta de vencimientos — el ciclo de alertas (agregado persistente, políticas, recordatorio, escalamiento) sigue detrás de `alertConfiguration`/`alertLifecycle`, capacidad distinta y no implementada.</p>}</>;
  if (page.id === 'legajos') return <><LegajosScreen detailId={detailId} />{technicalNotes && <p className="technical-note">GET /v1/consultas/sujetos y GET /v1/consultas/legajo integrados.</p>}</>;
  if (page.id === 'propuestas') return <><PropuestasScreen accessOverride={propuestasDeDiseno} readOnly={propuestasSoloLectura} />{technicalNotes && <p className="technical-note">Vista de diseño aislada con datos sintéticos y comandos deshabilitados. La pantalla operativa real integra propuestas fuera de este catálogo.</p>}</>;
  if (page.id === 'auditoria') return <><AuditoriaScreen />{technicalNotes && <p className="technical-note">GET /v1/consultas/log_auditoria implementado y con adaptador real (`realAuditoriaAccess`); activación detrás de `featureFlags.auditLogIntegration` (hoy `false`). El payload de cada evento se muestra tal cual lo entrega el servidor, sin interpretarlo del lado del cliente.</p>}</>;
  if (page.id === 'matrices') return <><MatricesScreen detailId={detailId} />{technicalNotes && <p className="technical-note">GET /v1/consultas/matrices y GET /v1/consultas/matriz_vigente integrados.</p>}</>;
  const fields = (selectors[page.id] || []).filter(([label]) => !label.includes('Responsable') || roles.includes('responsable_legajos'));
  return <><ReadViewDesign key={page.id} pageId={page.id} technicalNotes={technicalNotes} />{fields.length > 0 && <section className="panel"><h3>Selección de contexto</h3><div className="form-grid">{fields.map(([label, dependency]) => <BlockedSelector key={label} label={label} dependency={dependency} />)}</div></section>}
    {technicalNotes && <p className="technical-note">Dependencias: {page.gaps.join(' · ')}. No se ejecutan consultas de negocio desde esta lámina.</p>}
  </>;
}

