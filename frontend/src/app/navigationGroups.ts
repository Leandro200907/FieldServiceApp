import type { Page, PageId, Role } from './capabilities';
import { canOpen, pages } from './capabilities';

export type NavGroup = { title: string; pageIds: PageId[] };

const TRABAJO_DIARIO: PageId[] = ['propuestas', 'legajos', 'vencimientos', 'acciones-pendientes'];
const CONTROL: PageId[] = ['radar-documental', 'backlog-oc', 'timeline-recursos', 'auditoria'];
const REFERENCIAS: PageId[] = ['catalogos-oc', 'matrices'];

export function navigationGroupsFor(roles: readonly Role[]): NavGroup[] {
  const open = (ids: PageId[]) =>
    ids
      .map(id => pages.find(p => p.id === id))
      .filter((p): p is Page => Boolean(p && canOpen(p, roles)));

  const groups: NavGroup[] = [
    { title: 'Trabajo diario', pageIds: [] },
    { title: 'Control', pageIds: [] },
    { title: 'Referencias', pageIds: [] },
  ];
  groups[0] = { title: 'Trabajo diario', pageIds: open(TRABAJO_DIARIO).map(p => p.id) };
  groups[1] = { title: 'Control', pageIds: open(CONTROL).map(p => p.id) };
  groups[2] = { title: 'Referencias', pageIds: open(REFERENCIAS).map(p => p.id) };

  const out = groups.filter(g => g.pageIds.length > 0);

  const configPage = pages.find(p => p.id === 'configuracion');
  if (roles.includes('configuracion') && configPage && canOpen(configPage, roles)) {
    out.unshift({ title: 'Administración', pageIds: ['configuracion'] });
  }

  if (roles.includes('tecnico') && canOpen(pages.find(p => p.id === 'mi-legajo')!, roles)) {
    out.unshift({ title: 'Mi trabajo', pageIds: ['mi-legajo'] });
  }

  return out;
}

export function pageFromPath(pathname: string): Page | undefined {
  const root = pathname.split('/').filter(Boolean)[0] as PageId | undefined;
  return pages.find(p => p.id === root);
}

export function detailIdFromPath(pathname: string): string | undefined {
  const parts = pathname.split('/').filter(Boolean);
  return parts[1] || undefined;
}
