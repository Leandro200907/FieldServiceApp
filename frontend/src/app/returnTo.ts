import { canOpen, entryFor, knownRoles, pages, type Role } from './capabilities';
import { pageFromPath } from './navigationGroups';

const HOME_ROLE_PRIORITY: Role[] = ['configuracion', 'responsable_legajos', 'supervisor', 'tecnico'];

/** Pantalla de inicio según rol (misma lógica que post-login sin `return`). */
export function defaultHomePath(roles: readonly string[]): string {
  const known = knownRoles(roles);
  if (known.length === 0) return '/perfil';
  if (known.length === 1) return `/${entryFor(known[0])}`;
  const picked = HOME_ROLE_PRIORITY.find(role => known.includes(role)) ?? known[0];
  return `/${entryFor(picked)}`;
}

/** Rutas internas seguras para redirigir después del login (sin open redirect). */
export function isInternalReturn(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.startsWith('/login')) return false;
  try {
    const parsed = new URL(path, 'https://app.local');
    return parsed.origin === 'https://app.local' && parsed.pathname.startsWith('/');
  } catch {
    return false;
  }
}

export function loginPathWithReturn(pathname: string, search: string): string {
  const candidate = `${pathname}${search}`;
  if (!isInternalReturn(candidate)) return '/login';
  return `/login?return=${encodeURIComponent(candidate)}`;
}

/** Destino post-login: respeta `return` solo si el rol puede abrir esa pantalla. */
export function resolvePostLoginPath(returnTo: string | null | undefined, roles: readonly string[]): string {
  const known = knownRoles(roles);
  if (returnTo && isInternalReturn(returnTo)) {
    const pathOnly = returnTo.split('?')[0];
    const page = pageFromPath(pathOnly);
    if (page && canOpen(page, known)) return returnTo;
  }
  return defaultHomePath(known);
}
