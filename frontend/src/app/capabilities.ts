export const roleLabels = {
  configuracion: 'Configuración',
  responsable_legajos: 'Responsable de legajos',
  supervisor: 'Supervisor',
  tecnico: 'Técnico',
} as const;
export type Role = keyof typeof roleLabels;
export function knownRoles(roles: readonly string[]): Role[] {
  return [...new Set(roles.filter((role): role is Role => Object.hasOwn(roleLabels, role)))];
}
export type PageId = 'propuestas' | 'legajos' | 'mi-legajo' | 'equipo-supervisado' | 'vencimientos' | 'calendario-vigencias' | 'proyeccion-backlog' | 'oc' | 'matrices' | 'supervision' | 'auditoria' | 'custodias' | 'configuracion' | 'perfil';
export interface Page { id: PageId; label: string; description: string; roles: readonly Role[]; gaps: string[] }
export const pages: Page[] = [
  { id: 'configuracion', label: 'Configuración', description: 'Definiciones locales y administración documental.', roles: ['configuracion'], gaps: ['G-01', 'G-02'] },
  { id: 'propuestas', label: 'Propuestas', description: 'Revisión de documentación presentada por técnicos.', roles: ['responsable_legajos'], gaps: ['G-01', 'G-03'] },
  { id: 'legajos', label: 'Legajos', description: 'Documentación de personas, vehículos, equipos y empresa.', roles: ['responsable_legajos', 'supervisor'], gaps: ['G-01', 'SEL-01'] },
  // G-05/G-16 ya no son gaps de contrato — GET /v1/consultas/mi_legajo tiene adaptador
  // real (`realMiLegajoAccess.ts`), detrás de `featureFlags.technicianCompositeView`
  // (hoy `false`, decisión de producto, no gap de API). G-17 (separar "Mi legajo" de
  // "Equipo supervisado") sigue abierto, sin relación con esto.
  { id: 'mi-legajo', label: 'Mi legajo', description: 'Tu condición documental como persona potencialmente operativa.', roles: ['tecnico', 'supervisor'], gaps: ['G-17'] },
  { id: 'equipo-supervisado', label: 'Equipo supervisado', description: 'Personas y recursos dentro de tu universo asignado.', roles: ['supervisor'], gaps: ['G-01', 'G-17', 'SEL-33'] },
  // G-01 ya no es gap de contrato para este endpoint — GET /v1/consultas/tablero_vencimientos
  // tiene adaptador real (`realVencimientosAccess.ts`), detrás de
  // `featureFlags.expirationsBoardIntegration` (hoy `false`). H-02 sigue abierto: esta
  // pantalla es solo consulta, sin ciclo de alertas (agregado, políticas, recordatorio,
  // escalamiento) — capacidad distinta, no implementada.
  { id: 'vencimientos', label: 'Vencimientos', description: 'Evidencia vencida o próxima a vencer dentro de tu alcance.', roles: ['responsable_legajos', 'supervisor'], gaps: ['H-02'] },
  // F-08 (auditoría externa 2026-09-22): Q-DOC-01/02/03 y G-18 ya no son gaps de
  // contrato — los 4 endpoints están implementados y con adaptador real
  // (`realDocumentationPlanningAccess.ts`), sólo detrás de featureFlags en `false`
  // (decisión de producto, no un gap de API — ver docs/frontend/API_GAPS.md §8).
  { id: 'calendario-vigencias', label: 'Calendario documental', description: 'Intervalos documentales por empresa, persona, vehículo y equipo.', roles: ['responsable_legajos', 'supervisor', 'tecnico'], gaps: [] },
  { id: 'proyeccion-backlog', label: 'Proyección del backlog', description: 'Riesgo documental proyectado por OC, sin disponibilidad ni asignación.', roles: ['responsable_legajos', 'supervisor'], gaps: [] },
  { id: 'oc', label: 'OC y cobertura', description: 'Consulta de cobertura y decisiones registradas.', roles: ['responsable_legajos', 'supervisor'], gaps: ['G-01', 'G-07', 'SEL-18', 'SEL-19'] },
  { id: 'matrices', label: 'Matrices', description: 'Requisitos por cliente, locación y tipo de servicio.', roles: ['configuracion', 'responsable_legajos'], gaps: ['G-01', 'SEL-09', 'SEL-10', 'SEL-11', 'SEL-12'] },
  { id: 'supervision', label: 'Supervisión', description: 'Asignación e historial de supervisores.', roles: ['configuracion', 'responsable_legajos'], gaps: ['G-01', 'SEL-26', 'SEL-27'] },
  { id: 'custodias', label: 'Custodias', description: 'Asignación y corrección de la custodia de recursos.', roles: ['supervisor'], gaps: ['G-01', 'SEL-28', 'SEL-29', 'SEL-30'] },
  { id: 'auditoria', label: 'Auditoría', description: 'Consulta de eventos del módulo.', roles: ['configuracion', 'responsable_legajos'], gaps: ['G-01'] },
  { id: 'perfil', label: 'Mi sesión', description: 'Identidad y permisos de la sesión actual.', roles: ['configuracion', 'responsable_legajos', 'supervisor', 'tecnico'], gaps: [] },
];
export function canOpen(page: Page, roles: readonly string[]): boolean {
  return knownRoles(roles).some(role => page.roles.includes(role));
}
export function navigationFor(role: Role): Page[] { return pages.filter(page => page.roles.includes(role)); }
export function entryFor(role: Role): PageId {
  return { configuracion: 'configuracion', responsable_legajos: 'propuestas', supervisor: 'equipo-supervisado', tecnico: 'mi-legajo' }[role] as PageId;
}
