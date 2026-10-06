import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LegajoFicha } from '../src/features/legajos/LegajoFicha';
import { MiLegajoScreen } from '../src/features/mi-legajo/MiLegajoScreen';
import { MatricesScreen } from '../src/features/matrices/MatricesScreen';
import { AccionesPendientesScreen } from '../src/features/documentation-planning/AccionesPendientesScreen';
import { BacklogOcScreen } from '../src/features/documentation-planning/BacklogOcScreen';
import { CalendarDocumentalScreen } from '../src/features/documentation-planning/CalendarDocumentalScreen';
import { TimelineRecursosScreen } from '../src/features/documentation-planning/TimelineRecursosScreen';
import { deriveVisualState } from '../src/features/documentation-planning/contracts';
import {
  HOY_TENANT,
  accionesFixture,
  backlogFixture,
  calendarioFixture,
  legajoConsultaFixture,
  matricesFixture,
  miLegajoFixture,
  timelineFixture,
} from './fixtures/reglaUnicaBackend';

const reads = vi.hoisted(() => ({
  queue: [] as unknown[],
  push: (...values: unknown[]) => {
    reads.queue.push(...values);
  },
  reset: () => {
    reads.queue = [];
  },
  next: () => reads.queue.shift(),
}));

const routerSearch = vi.hoisted(() => ({
  params: new URLSearchParams(),
}));

vi.mock('../src/api/session', () => ({
  session: {
    getSnapshot: () => ({
      identity: {
        zona_horaria: 'America/Argentina/Buenos_Aires',
        roles: ['responsable_legajos', 'configuracion'],
      },
    }),
  },
  ApiFailure: class ApiFailure extends Error {},
  parseApiError: () => ({ message: 'error' }),
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

vi.mock('../src/features/legajos/access', () => ({
  legajosAccess: () => ({ readEspejoOperadora: async () => ({ items: [] }) }),
}));

vi.mock('../src/features/mi-legajo/access', () => ({
  miLegajoAccess: () => ({ readMiLegajo: async () => miLegajoFixture }),
}));

vi.mock('../src/features/matrices/access', () => ({
  matricesAccess: () => ({
    readMatrices: async () => matricesFixture,
    readMatrizVigente: async () => null,
  }),
}));

vi.mock('../src/features/documentation-planning/access', () => ({
  calendarAccess: () => ({ readCalendar: async () => calendarioFixture }),
  documentationPlanningAccess: () => ({}),
}));

describe('regla única — pantallas consumen campos del backend', () => {
  beforeEach(() => {
    reads.reset();
    routerSearch.params = new URLSearchParams();
  });

  it('LegajoFicha: tarjetas exigidos, pendientes y próximo vencimiento del resumen', () => {
    const html = renderToStaticMarkup(
      createElement(LegajoFicha, {
        data: legajoConsultaFixture,
        sujetoId: 'persona_demo',
        onClose: () => {},
      }),
    );
    expect(html).toContain('<strong>1</strong><span>Vencidos</span>');
    expect(html).toContain('<strong>2</strong><span>Vigentes</span>');
    expect(html).toContain('2 pendientes de revisar');
    expect(html).toContain('20/11/2026');
  });

  it('MiLegajoScreen: badge con en_regla_exigidos y exigidos', () => {
    reads.push(miLegajoFixture);
    const html = renderToStaticMarkup(createElement(MiLegajoScreen));
    expect(html).toContain('2 de 3 en regla (exigidos por OC)');
    expect(html).toContain('Hoy: 18/09/2026');
  });

  it('MatricesScreen: vigente_hoy del ítem (v2 vigente)', () => {
    reads.push({ operadoras: [] });
    reads.push(matricesFixture);
    const html = renderToStaticMarkup(createElement(MatricesScreen, {}));
    expect(html).toContain('v2 vigente');
  });

  it('AccionesPendientesScreen: accion_vencida del ítem', () => {
    reads.push({ operadoras: [] });
    reads.push(accionesFixture);
    const html = renderToStaticMarkup(
      createElement(MemoryRouter, { initialEntries: ['/acciones-pendientes'] }, createElement(AccionesPendientesScreen)),
    );
    expect(html).toContain('accion-vencida');
    expect(html).toContain('Apto médico');
  });

  it('BacklogOcScreen: hoy del tenant en el Gantt', () => {
    routerSearch.params = new URLSearchParams('vista=mapa');
    reads.push({ operadoras: [] });
    reads.push(backlogFixture);
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/backlog-oc?vista=mapa'] },
        createElement(BacklogOcScreen, { roles: ['responsable_legajos'] }),
      ),
    );
    expect(html).toContain('title="Hoy"');
  });

  it('Calendario: hoy del API y estado_visual_calendario', () => {
    reads.push(calendarioFixture);
    const html = renderToStaticMarkup(createElement(CalendarDocumentalScreen, { roles: ['responsable_legajos'] }));
    expect(html).toContain('Hoy · 18/09/2026');
    expect(deriveVisualState(calendarioFixture.items[0])).toBe('verificada');
    expect(html).toContain('Verificada');
  });

  it('TimelineRecursosScreen: hoy del API en cabecera', () => {
    reads.push(timelineFixture);
    const html = renderToStaticMarkup(createElement(TimelineRecursosScreen, { roles: ['responsable_legajos'] }));
    expect(html).toContain('Hoy: 18/09/2026');
  });
});
