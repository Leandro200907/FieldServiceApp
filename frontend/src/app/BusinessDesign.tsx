import { ReadViewDesign } from './ReadViewDesign';
import type { Page } from './capabilities';
import { BlockedSelector, Pending } from '../ui/States';
import { CalendarDocumentalScreen } from '../features/documentation-planning/CalendarDocumentalScreen';
import { BacklogProjectionScreen } from '../features/documentation-planning/BacklogProjectionScreen';
import { MiLegajoScreen } from '../features/mi-legajo/MiLegajoScreen';
import { VencimientosScreen } from '../features/vencimientos/VencimientosScreen';
import { LegajosScreen } from '../features/legajos/LegajosScreen';

const selectors: Partial<Record<Page['id'], Array<[string, string]>>> = {
  matrices: [['Cliente', 'SEL-09 · catálogo pendiente'], ['Locación', 'SEL-10 · catálogo pendiente'], ['Tipo de servicio', 'SEL-11 · catálogo pendiente'], ['Requisito de la línea', 'SEL-12 · catálogo existente; integración pendiente']],
  supervision: [['Persona', 'SEL-26 · consulta existente; integración pendiente'], ['Supervisor', 'SEL-27 · consulta existente; integración pendiente']],
  custodias: [['Vehículo o equipo', 'SEL-28 · recursos autorizados pendientes'], ['Custodio', 'SEL-29 · personas autorizadas pendientes'], ['Período a corregir', 'SEL-30 · historial pendiente']],
  oc: [['OC / compromiso', 'SEL-18 · contrato tipado candidato; integración pendiente'], ['Sujetos para decisión del Responsable', 'SEL-19 · sujetos existentes; alcance pendiente de validación']],
  configuracion: [['Definición local', 'SEL-13 · catálogo existente; integración pendiente']],
};
export function BusinessDesign({ page, technicalNotes = false, roles = [] }: { page: Page; technicalNotes?: boolean; roles?: readonly string[] }) {
  if (page.id === 'calendario-vigencias') return <><CalendarDocumentalScreen roles={roles} />{technicalNotes && <p className="technical-note">Q-DOC-01 · GET /v1/consultas/calendario_vigencias implementado y con adaptador real (`realDocumentationPlanningAccess`); activación detrás de `featureFlags.documentationCalendarIntegration` (hoy `false`). Q-DOC-03 (GET /v1/consultas/detalle_proyeccion_documental, detalle de tramo por referencia) también implementado en el backend — el frontend todavía no lo consume desde esta pantalla (F-08).</p>}</>;
  if (page.id === 'proyeccion-backlog') return <><BacklogProjectionScreen roles={roles} />{technicalNotes && <p className="technical-note">Q-DOC-02 · GET /v1/consultas/proyeccion_documental_backlog y GET /v1/consultas/proyeccion_documental (detalle) implementados y con adaptador real; activación detrás de `featureFlags.backlogDocumentationIntegration` (hoy `false`). No contiene funciones del Módulo 2.</p>}</>;
  if (page.id === 'mi-legajo') return <><MiLegajoScreen />{technicalNotes && <p className="technical-note">G-05 / G-16 · GET /v1/consultas/mi_legajo implementado y con adaptador real (`realMiLegajoAccess`); activación detrás de `featureFlags.technicianCompositeView` (hoy `false`). A-01 (auditoría de custodias) resuelto — ya no aplica como bloqueo. Sin selector: el servidor resuelve el sujeto propio desde el JWT, nunca un id elegido por el cliente.</p>}</>;
  if (page.id === 'vencimientos') return <><VencimientosScreen />{technicalNotes && <p className="technical-note">G-01 / H-02 · GET /v1/consultas/tablero_vencimientos implementado, tipado y con adaptador real (`realVencimientosAccess`); activación detrás de `featureFlags.expirationsBoardIntegration` (hoy `false`). Muestra solo la consulta de vencimientos — el ciclo de alertas (agregado persistente, políticas, recordatorio, escalamiento) sigue detrás de `alertConfiguration`/`alertLifecycle`, capacidad distinta y no implementada.</p>}</>;
  if (page.id === 'legajos') return <><LegajosScreen />{technicalNotes && <p className="technical-note">SEL-01 · GET /v1/consultas/sujetos (búsqueda) y GET /v1/consultas/legajo (detalle por sujeto_id) implementados y con adaptador real (`realLegajosAccess`); activación detrás de `featureFlags.legajoLookupIntegration` (hoy `false`). El sujeto elegido siempre sale de una búsqueda ya acotada al alcance del usuario, nunca de un id libre.</p>}</>;
  if (page.id === 'equipo-supervisado') return <>
    <Pending title="Tu equipo espera la validación del alcance">Este contexto mostrará únicamente las personas, vehículos y equipos asignados al Supervisor. El contexto personal se consulta en Mi legajo. La consulta actual acumula alcance propio y supervisado: falta distinguir ambos de forma fiable, sin deducir asignaciones en el frontend.</Pending>
    <section className="panel"><h3>Universo asignado</h3><div className="form-grid"><BlockedSelector label="Persona o recurso supervisado" dependency="SEL-33 · falta separar alcance personal y supervisado" /></div><p>Las vistas de vencimientos, cobertura, custodias y evidencia conservarán el alcance aplicado por el servidor.</p></section>
    {technicalNotes && <p className="technical-note">G-17 / SEL-33 · Separación entre identidad personal y responsabilidad de supervisión.</p>}
  </>;
  const fields = (selectors[page.id] || []).filter(([label]) => !label.includes('Responsable') || roles.includes('responsable_legajos'));
  return <><ReadViewDesign key={page.id} pageId={page.id} technicalNotes={technicalNotes} />{fields.length > 0 && <section className="panel"><h3>Selección de contexto</h3><div className="form-grid">{fields.map(([label, dependency]) => <BlockedSelector key={label} label={label} dependency={dependency} />)}</div></section>}
    {page.id === 'oc' && <section className="panel"><h3>Consulta y decisión</h3><p>Consultar cobertura no registra una decisión ni asigna una orden de trabajo. La evaluación persistida será una acción explícita del Responsable de legajos.</p></section>}
    {page.id === 'propuestas' && <section className="panel"><h3>Revisión documental</h3><p>La bandeja, la descarga de evidencia y las acciones de confirmar o rechazar cuentan con un contrato tipado candidato. La conexión y las acciones siguen pendientes de validación.</p></section>}
    {technicalNotes && <p className="technical-note">Dependencias: {page.gaps.join(' · ')}. No se ejecutan consultas de negocio desde esta lámina.</p>}
  </>;
}
