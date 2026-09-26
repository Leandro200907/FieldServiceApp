import { describe, expect, it } from 'vitest';
import { entryFor, navigationFor, pages } from '../src/app/capabilities';

describe('Módulo 1 navigation', () => {
  it('shows the documentary radar and excludes assignment flows', () => {
    expect(pages.map(page => page.id)).toContain('radar-documental');
    expect(pages.map(page => page.id)).not.toEqual(expect.arrayContaining(['equipo-supervisado', 'supervision', 'custodias', 'oc']));
  });

  it('opens the supervisor in the documentary radar', () => {
    expect(entryFor('supervisor')).toBe('radar-documental');
    expect(navigationFor('supervisor').map(page => page.id)).not.toContain('mi-legajo');
  });

  it('keeps people, vehicles and equipment as documentary subjects', () => {
    expect(pages.find(page => page.id === 'legajos')?.description).toMatch(/personas, vehículos, equipos/);
  });
});


