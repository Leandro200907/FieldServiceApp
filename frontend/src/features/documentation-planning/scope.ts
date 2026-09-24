import type { DocumentationScope } from './contracts';

// Solo para etiquetas/UI — el alcance real de datos lo resuelve el backend con el JWT
// (`alcance_de_sujetos`), nunca este valor. Devuelve `null` en vez de adivinar cuando el
// rol no tiene ninguna de las tres pantallas de este feature (p. ej. `configuracion`, que
// no puede consultar calendario/proyección/backlog — 403 real del lado del servidor si de
// todos modos se intentara). Antes caía silenciosamente a `'technician'` para cualquier
// rol no reconocido; el enrutado (`app/flags.ts::canOpen`) ya impide llegar a estas
// pantallas sin uno de los tres roles habilitados, así que esto es defensa en profundidad,
// no el control de acceso real.
export function documentationScopeFor(roles: readonly string[]): DocumentationScope | null {
  if (roles.includes('responsable_legajos')) return 'responsible';
  if (roles.includes('supervisor')) return 'supervisor';
  if (roles.includes('tecnico')) return 'technician';
  return null;
}
