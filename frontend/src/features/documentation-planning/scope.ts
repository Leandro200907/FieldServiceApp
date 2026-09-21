import type { DocumentationScope } from './contracts';

export function documentationScopeFor(roles: readonly string[]): DocumentationScope {
  if (roles.includes('responsable_legajos')) return 'responsible';
  if (roles.includes('supervisor')) return 'supervisor';
  return 'technician';
}
