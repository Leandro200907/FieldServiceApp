import type { Page } from './capabilities';
import { Badge, BlockedSelector, Pending } from '../ui/States';

const selectors: Partial<Record<Page['id'], Array<[string, string]>>> = {
  legajos: [['Sujeto', 'SEL-01 · consulta de sujetos pendiente']],
  matrices: [['Cliente', 'SEL-09 · catálogo pendiente'], ['Locación', 'SEL-10 · catálogo pendiente'], ['Tipo de servicio', 'SEL-11 · catálogo pendiente'], ['Requisito de la línea', 'SEL-12 · catálogo pendiente']],
  supervision: [['Persona', 'SEL-26 · consulta pendiente'], ['Supervisor', 'SEL-27 · consulta pendiente']],
  custodias: [['Vehículo o equipo', 'SEL-28 · recursos autorizados pendientes'], ['Custodio', 'SEL-29 · personas autorizadas pendientes'], ['Período a corregir', 'SEL-30 · historial pendiente']],
  oc: [['OC / compromiso', 'SEL-18 · respuesta de backlog sin tipar'], ['Sujetos para decisión del Responsable', 'SEL-19 · consulta pendiente']],
  configuracion: [['Definición local', 'SEL-13 · catálogo pendiente']],
};
export function BusinessDesign({ page, technicalNotes = false, roles = [] }: { page: Page; technicalNotes?: boolean; roles?: readonly string[] }) {
  if (page.id === 'mi-legajo' && roles.includes('supervisor') && !roles.includes('tecnico')) return <>
    <Pending title="Tu legajo personal está pendiente de integración">Este contexto representa tu situación documental como persona potencialmente operativa. Tener rol Supervisor no demuestra que estés documentalmente habilitado. La habilitación debe venir expresamente del backend.</Pending>
    <section className="panel resource-panel"><div className="panel-top"><span className="section-number">01</span><Badge tone="warning">Integración bloqueada</Badge></div><h3>Mi condición documental</h3><p>Identidad, documentos, competencias, inducciones y veredicto explícito del servidor para la persona asociada al usuario.</p><div className="resource-placeholder" aria-hidden="true"><span /><span /><span /></div></section>
    {technicalNotes && <p className="technical-note">G-17 · El rol Supervisor no es evidencia de habilitación y este contexto no representa al equipo supervisado.</p>}
  </>;
  if (page.id === 'mi-legajo') return <>
    <Pending title="Tu legajo compuesto está pendiente de integración">La consulta debe reunir tu persona, el vehículo vigente y los equipos bajo tu custodia. La falta de conexión no significa que no tengas recursos asignados.</Pending>
    <div className="composite-grid">{[
      ['01', 'Persona', 'Identidad, documentación, competencias e inducciones de tu propio legajo. Ningún estado de habilitación se presume por el rol.'],
      ['02', 'Vehículo vigente', 'Vehículo, período de custodia y evidencia que el servidor autorice a consultar.'],
      ['03', 'Equipos bajo custodia', 'Equipos vigentes y documentación accesible dentro de tu alcance.'],
    ].map(([number, title, copy]) => <section className="panel resource-panel" key={title}><div className="panel-top"><span className="section-number">{number}</span><Badge tone="warning">Integración bloqueada</Badge></div><h3>{title}</h3><p>{copy}</p><div className="resource-placeholder" aria-hidden="true"><span /><span /><span /></div></section>)}</div>
    {technicalNotes && <p className="technical-note">G-05 / G-16 · Sin selectores de persona o recursos. La propuesta de consulta compuesta no está implementada ni se utiliza en mocks.</p>}
  </>;
  if (page.id === 'equipo-supervisado') return <>
    <Pending title="El universo supervisado espera una consulta autorizada">Este contexto mostrará únicamente las personas, vehículos y equipos asignados al Supervisor. No incluye su legajo personal ni presume que el Supervisor esté habilitado para operar.</Pending>
    <section className="panel"><h3>Universo asignado</h3><div className="form-grid"><BlockedSelector label="Persona o recurso supervisado" dependency="SEL-33 · consulta del universo pendiente" /></div><p>Las vistas de vencimientos, cobertura, custodias y evidencia conservarán el alcance aplicado por el servidor.</p></section>
    {technicalNotes && <p className="technical-note">G-17 / SEL-33 · Separación entre identidad personal y responsabilidad de supervisión.</p>}
  </>;
  const fields = (selectors[page.id] || []).filter(([label]) => !label.includes('Responsable') || roles.includes('responsable_legajos'));
  return <><Pending />{fields.length > 0 && <section className="panel"><h3>Selección de contexto</h3><div className="form-grid">{fields.map(([label, dependency]) => <BlockedSelector key={label} label={label} dependency={dependency} />)}</div></section>}
    {page.id === 'vencimientos' && <section className="panel"><h3>Vencimientos y alertas</h3><p>La consulta de evidencia y el ciclo de recordatorios y escalamiento son capacidades distintas. Esta pantalla todavía no muestra resultados de ninguna de ellas.</p></section>}
    {page.id === 'oc' && <section className="panel"><h3>Consulta y decisión</h3><p>Consultar cobertura no registra una decisión ni asigna una orden de trabajo. La evaluación persistida será una acción explícita del Responsable de legajos.</p></section>}
    {page.id === 'propuestas' && <section className="panel"><h3>Revisión documental</h3><p>La bandeja, la descarga de evidencia y las acciones de confirmar o rechazar se conectarán cuando sus respuestas estén tipadas.</p></section>}
    {technicalNotes && <p className="technical-note">Dependencias: {page.gaps.join(' · ')}. No se ejecutan consultas de negocio desde esta lámina.</p>}
  </>;
}
