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

export type PageId = 'propuestas' | 'legajos' | 'mi-legajo' | 'vencimientos' | 'calendario-vigencias' | 'radar-documental' | 'backlog-oc' | 'timeline-recursos' | 'acciones-pendientes' | 'catalogos-oc' | 'matrices' | 'auditoria' | 'configuracion' | 'perfil';
export interface Page { id: PageId; label: string; description: string; roles: readonly Role[]; gaps: string[] }

export const pages: Page[] = [
  { id: 'configuracion', label: 'Configuración', description: 'Definiciones locales y administración documental.', roles: ['configuracion'], gaps: ['G-01', 'G-02'] },
  { id: 'propuestas', label: 'Propuestas', description: 'Revisión de documentación presentada.', roles: ['responsable_legajos'], gaps: ['G-03'] },
  { id: 'legajos', label: 'Legajos', description: 'Documentación de personas, vehículos, equipos y empresa.', roles: ['responsable_legajos', 'supervisor'], gaps: [] },
  { id: 'mi-legajo', label: 'Mi legajo', description: 'Tu documentación personal registrada.', roles: ['tecnico'], gaps: [] },
  { id: 'vencimientos', label: 'Vencimientos', description: 'Evidencia vencida o próxima a vencer dentro de tu alcance documental.', roles: ['responsable_legajos', 'supervisor'], gaps: ['H-02'] },
  { id: 'calendario-vigencias', label: 'Calendario documental', description: 'Vigencias documentales de empresas, personas, vehículos y equipos.', roles: ['responsable_legajos', 'supervisor', 'tecnico'], gaps: [] },
  { id: 'radar-documental', label: 'Radar de OC', description: 'Señales documentales informativas sobre las OC previstas.', roles: ['responsable_legajos', 'supervisor'], gaps: [] },
  { id: 'backlog-oc', label: 'Backlog de OC', description: 'Órdenes de compra con disponibilidad documental en vivo.', roles: ['responsable_legajos', 'supervisor'], gaps: [] },
  { id: 'acciones-pendientes', label: 'Acciones pendientes', description: 'Renovaciones y regularizaciones que afectan OCs activas.', roles: ['responsable_legajos', 'supervisor'], gaps: [] },
  { id: 'timeline-recursos', label: 'Línea de tiempo', description: 'Vigencias por recurso y cruces con ventanas de OC.', roles: ['responsable_legajos', 'supervisor', 'configuracion', 'tecnico'], gaps: [] },
  { id: 'catalogos-oc', label: 'Catálogos OC', description: 'Operadoras, locaciones y tipos de servicio para planillas de OC.', roles: ['responsable_legajos', 'configuracion'], gaps: [] },
  { id: 'matrices', label: 'Matrices', description: 'Requisitos por cliente, locación y tipo de servicio.', roles: ['configuracion', 'responsable_legajos'], gaps: ['SEL-09', 'SEL-10', 'SEL-11'] },
  { id: 'auditoria', label: 'Auditoría', description: 'Consulta de eventos del módulo.', roles: ['configuracion', 'responsable_legajos'], gaps: [] },
  { id: 'perfil', label: 'Mi sesión', description: 'Identidad y permisos de la sesión actual.', roles: ['configuracion', 'responsable_legajos', 'supervisor', 'tecnico'], gaps: [] },
];

export function canOpen(page: Page, roles: readonly string[]): boolean {
  return knownRoles(roles).some(role => page.roles.includes(role));
}
export function navigationFor(role: Role): Page[] { return pages.filter(page => page.roles.includes(role)); }
export function entryFor(role: Role): PageId {
  return { configuracion: 'configuracion', responsable_legajos: 'propuestas', supervisor: 'radar-documental', tecnico: 'mi-legajo' }[role] as PageId;
}


