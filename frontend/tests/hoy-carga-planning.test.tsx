import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BacklogOcScreen } from '../src/features/documentation-planning/BacklogOcScreen';
import { TimelineRecursosScreen } from '../src/features/documentation-planning/TimelineRecursosScreen';
import { AccionesPendientesScreen } from '../src/features/documentation-planning/AccionesPendientesScreen';
import { CalendarDocumentalScreen } from '../src/features/documentation-planning/CalendarDocumentalScreen';
import { HOY_TENANT, accionesFixture, backlogFixture, calendarioFixture, timelineFixture } from './fixtures/reglaUnicaBackend';

const reads = vi.hoisted(() => ({
  queue: [] as unknown[],
  reset: () => {
    reads.queue = [];
  },
  next: () => reads.queue.shift(),
}));

const routerSearch = vi.hoisted(() => ({
  params: new URLSearchParams(),
}));

vi.mock('../src/api', () => ({
  session: {
    getSnapshot: () => ({
      identity: {
        zona_horaria: 'America/Argentina/Buenos_Aires',
        roles: ['responsable_legajos', 'configuracion'],
      },
    }),
    client: { GET: vi.fn(), POST: vi.fn() },
  },
  ApiFailure: class ApiFailure extends Error {},
  parseApiError: () => ({ message: 'error' }),
}));

vi.mock('../src/hooks/usePrototypeRead', () => ({
  usePrototypeRead: () => {
    const data = reads.next();
    return { loading: data === undefined, error: null, data };
  },
  esCargaInicial: (q: { loading: boolean; data?: unknown }) => q.loading && q.data === undefined,
}));

vi.mock('react-router-dom', async importOriginal => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => () => {},
    useParams: () => ({}),
    useSearchParams: () => [routerSearch.params, () => {}],
  };
});

describe('carga con hoy del backend', () => {
  beforeEach(() => {
    reads.reset();
    routerSearch.params = new URLSearchParams();
  });

  it('BacklogOcScreen: primer render sin datos muestra carga y no dibuja Gantt', () => {
    routerSearch.params = new URLSearchParams('vista=mapa');
    const html = renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: ['/backlog-oc?vista=mapa'] }, createElement(BacklogOcScreen, { roles: ['responsable_legajos'] })),
    );
    expect(html.toLowerCase()).toContain('cargando');
    expect(html).not.toContain('title="Hoy"');
  });

  it('BacklogOcScreen: con hoy del API muestra el marcador Hoy', () => {
    routerSearch.params = new URLSearchParams('vista=mapa');
    reads.queue.push({ operadoras: [] }, backlogFixture);
    const html = renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: ['/backlog-oc?vista=mapa'] }, createElement(BacklogOcScreen, { roles: ['responsable_legajos'] })),
    );
    expect(html).toContain('title="Hoy"');
  });

  it('TimelineRecursosScreen: sin datos muestra carga', () => {
    const html = renderToStaticMarkup(createElement(TimelineRecursosScreen, { roles: ['responsable_legajos'] }));
    expect(html.toLowerCase()).toContain('cargando');
  });

  it('TimelineRecursosScreen: con fixture muestra Hoy del tenant', () => {
    reads.queue.push(timelineFixture);
    const html = renderToStaticMarkup(createElement(TimelineRecursosScreen, { roles: ['responsable_legajos'] }));
    expect(html).toContain('Hoy: 18/09/2026');
  });

  it('AccionesPendientesScreen: sin hoy del API queda en carga', () => {
    reads.queue.push({ operadoras: [] });
    const html = renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: ['/acciones-pendientes'] }, createElement(AccionesPendientesScreen)),
    );
    expect(html.toLowerCase()).toContain('cargando');
  });

  it('AccionesPendientesScreen: con hoy muestra la tabla', () => {
    reads.queue.push({ operadoras: [] }, accionesFixture);
    const html = renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: ['/acciones-pendientes'] }, createElement(AccionesPendientesScreen)),
    );
    expect(html).toContain('Acciones pendientes');
    expect(html).toContain('Apto médico');
  });

  it('Calendario: sin rango inicial no usa 2020-2035', () => {
    reads.queue.push(calendarioFixture);
    const html = renderToStaticMarkup(createElement(CalendarDocumentalScreen, { roles: ['responsable_legajos'] }));
    expect(html).not.toContain('01/01/2020');
    expect(html).toContain('Hoy · 18/09/2026');
  });
});
