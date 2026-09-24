import { describe, expect, it } from 'vitest';
import { canOpen, entryFor, navigationFor, pages } from '../src/app/capabilities';

describe('role navigation boundaries', () => {
  it('separates the supervisor personal and assigned-universe contexts', () => {
    const ids = navigationFor('supervisor').map(page => page.id);
    expect(ids).toContain('mi-legajo');
    expect(ids).toContain('equipo-supervisado');
    expect(entryFor('supervisor')).toBe('equipo-supervisado');
  });

  it('does not grant supervisor-only pages to a technician', () => {
    const team = pages.find(page => page.id === 'equipo-supervisado');
    expect(team).toBeDefined();
    expect(canOpen(team!, ['tecnico'])).toBe(false);
    expect(canOpen(team!, ['supervisor'])).toBe(true);
  });

  it('exposes documentary planning prototypes only to their intended roles', () => {
    const calendar = pages.find(page => page.id === 'calendario-vigencias');
    const backlog = pages.find(page => page.id === 'proyeccion-backlog');
    expect(canOpen(calendar!, ['tecnico'])).toBe(true);
    expect(canOpen(backlog!, ['tecnico'])).toBe(false);
    expect(canOpen(backlog!, ['supervisor'])).toBe(true);
    expect(canOpen(backlog!, ['responsable_legajos'])).toBe(true);
    expect(canOpen(calendar!, ['configuracion'])).toBe(false);
  });

  it('does not infer access from unknown roles', () => {
    expect(pages.some(page => canOpen(page, ['superadmin']))).toBe(false);
  });
});
