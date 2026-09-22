import { ReadViewDesign } from './ReadViewDesign';
import type { Page } from './capabilities';
import { Badge, BlockedSelector, Pending } from '../ui/States';
import { CalendarDocumentalScreen } from '../features/documentation-planning/CalendarDocumentalScreen';
import { BacklogProjectionScreen } from '../features/documentation-planning/BacklogProjectionScreen';

const selectors: Partial<Record<Page['id'], Array<[string, string]>>> = {
  legajos: [['Sujeto', 'SEL-01 · consulta existente; integración pendiente']],
  matrices: [['Cliente', 'SEL-09 · catálogo pendiente'], ['Locación', 'SEL-10 · catálogo pendiente'], ['Tipo de servicio', 'SEL-11 · catálogo pendiente'], ['Requisito de la línea', 'SEL-12 · catálogo existente; integración pendiente']],
  supervision: [['Persona', 'SEL-26 · consulta existente; integración pendiente'], ['Supervisor', 'SEL-27 · consulta existente; integración pendiente']],
  custodias: [['Vehículo o equipo', 'SEL-28 · recursos autorizados pendientes'], ['Custodio', 'SEL-29 · personas autorizadas pendientes'], ['Período a corregir', 'SEL-30 · historial pendiente']],
  oc: [['OC / compromiso', 'SEL-18 · contrato tipado candidato; integración pendiente'], ['Sujetos para decisión del Responsable', 'SEL-19 · sujetos existentes; alcance pendiente de validación']],
  configuracion: [['Definición local', 'SEL-13 · catálogo existente; integración pendiente']],
};
export function BusinessDesign({ page, technicalNotes = false, roles = [] }: { page: Page; technicalNotes?: boolean; roles?: readonly string[] }) {
  if (page.id === 'calendario-vigencias') return <><CalendarDocumentalScreen roles={roles} />{technicalNotes && <p className="technical-note">Q-DOC-01 · GET /v1/consultas/calendario_vigencias implementado y con adaptador real (`realDocumentationPlanningAccess`); activación detrás de `featureFlags.documentationCalendarIntegration` (hoy `false`). Q-DOC-03 (GET /v1/consultas/detalle_proyeccion_documental, detalle de tramo por referencia) también implementado en el backend — el frontend todavía no lo consume desde esta pantalla (F-08).</p>}</>;
  if (page.id === 'proyeccion-backlog') return <><BacklogProjectionScreen roles={roles} />{technicalNotes && <p className="technical-note">Q-DOC-02 · GET /v1/consultas/proyeccion_documental_backlog y GET /v1/consultas/proyeccion_documental (detalle) implementados y con adaptador real; activación detrás de `featureFlags.backlogDocumentationIntegration` (hoy `false`). No contiene funciones del Módulo 2.</p>}</>;
  if (page.id === 'mi-legajo') return <>
    {/* F-11 (auditoría externa 2026-09-22): esta lámina citaba A-01 (transferencia futura
        de custodia) como el bloqueo — A-01 está resuelto en el backend desde hace varias
        revisiones. Lo que falta acá es distinto: nadie construyó todavía un adaptador
        real (mismo patrón que `realDocumentationPlanningAccess` para calendario/backlog)
        — no hay ningún bug pendiente, es trabajo de integración sin empezar. */}
    <Pending title="Tu legajo compuesto está pendiente de integración">La consulta compuesta ya existe en el backend — reuniría tu persona, los vehículos vigentes y los equipos bajo tu custodia — pero el frontend todavía no tiene un adaptador real que la use, sólo esta lámina de diseño. La falta de conexión no significa que no tengas recursos asignados.</Pending>
    <div className="composite-grid">{[
      ['01', 'Persona', 'Identidad, documentación, competencias e inducciones de tu propio legajo. Ningún estado de habilitación se presume por el rol.'],
      ['02', 'Vehículos vigentes', 'Vehículo, período de custodia y evidencia que el servidor autorice a consultar.'],
      ['03', 'Equipos bajo custodia', 'Equipos vigentes y documentación accesible dentro de tu alcance.'],
    ].map(([number, title, copy]) => <section className="panel resource-panel" key={title}><div className="panel-top"><span className="section-number">{number}</span><Badge tone="warning">Integración bloqueada</Badge></div><h3>{title}</h3><p>{copy}</p><div className="resource-placeholder" aria-hidden="true"><span /><span /><span /></div></section>)}</div>
    {technicalNotes && <p className="technical-note">G-05 / G-16 · Sin selectores de persona o recursos. GET /v1/consultas/mi_legajo existe en db400e6; A-01 (auditoría de custodias) ya está resuelto — lo que falta es un adaptador real, todavía sin construir. No se presume un único vehículo.</p>}
  </>;
  if (page.id === 'equipo-supervisado') return <>
    <Pending title="Tu equipo espera la validación del alcance">Este contexto mostrará únicamente las personas, vehículos y equipos asignados al Supervisor. El contexto personal se consulta en Mi legajo. La consulta actual acumula alcance propio y supervisado: falta distinguir ambos de forma fiable, sin deducir asignaciones en el frontend.</Pending>
    <section className="panel"><h3>Universo asignado</h3><div className="form-grid"><BlockedSelector label="Persona o recurso supervisado" dependency="SEL-33 · falta separar alcance personal y supervisado" /></div><p>Las vistas de vencimientos, cobertura, custodias y evidencia conservarán el alcance aplicado por el servidor.</p></section>
    {technicalNotes && <p className="technical-note">G-17 / SEL-33 · Separación entre identidad personal y responsabilidad de supervisión.</p>}
  </>;
  const fields = (selectors[page.id] || []).filter(([label]) => !label.includes('Responsable') || roles.includes('responsable_legajos'));
  return <><ReadViewDesign key={page.id} pageId={page.id} technicalNotes={technicalNotes} />{fields.length > 0 && <section className="panel"><h3>Selección de contexto</h3><div className="form-grid">{fields.map(([label, dependency]) => <BlockedSelector key={label} label={label} dependency={dependency} />)}</div></section>}
    {page.id === 'vencimientos' && <section className="panel"><h3>Vencimientos y alertas</h3><p>La consulta de evidencia y el ciclo de recordatorios y escalamiento son capacidades distintas. Esta pantalla todavía no muestra resultados de ninguna de ellas.</p></section>}
    {page.id === 'oc' && <section className="panel"><h3>Consulta y decisión</h3><p>Consultar cobertura no registra una decisión ni asigna una orden de trabajo. La evaluación persistida será una acción explícita del Responsable de legajos.</p></section>}
    {page.id === 'propuestas' && <section className="panel"><h3>Revisión documental</h3><p>La bandeja, la descarga de evidencia y las acciones de confirmar o rechazar cuentan con un contrato tipado candidato. La conexión y las acciones siguen pendientes de validación.</p></section>}
    {technicalNotes && <p className="technical-note">Dependencias: {page.gaps.join(' · ')}. No se ejecutan consultas de negocio desde esta lámina.</p>}
  </>;
}
