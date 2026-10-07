import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MatricesScreen } from '../src/features/matrices/MatricesScreen';
import { MatrizNuevaScreen } from '../src/features/matrices/MatrizNuevaScreen';
import { MatrizEditorScreen } from '../src/features/matrices/MatrizEditorScreen';
import { PlantillaActualizacionScreen } from '../src/features/matrices/PlantillaActualizacionScreen';
import { BacklogOcScreen } from '../src/features/documentation-planning/BacklogOcScreen';
import { matricesFixture } from './fixtures/reglaUnicaBackend';
import { backlogSinMatrizFixture, catalogosOcMatricesFixture, plantillasConCambiosFixture } from './fixtures/matricesScreens';
import { saveMatrizDraft } from '../src/features/matrices/matrizDraft';

const reads: unknown[] = [];

vi.mock('../src/hooks/usePrototypeRead', () => ({
  usePrototypeRead: (fn: () => Promise<unknown>) => {
    const data = reads.length ? reads.shift() : undefined;
    return { data, loading: false, error: null };
  },
  esCargaInicial: () => false,
}));

vi.mock('../src/api', () => ({
  session: {
    getSnapshot: () => ({
      identity: { roles: ['responsable_legajos'], zona_horaria: 'America/Argentina/Buenos_Aires' },
    }),
    client: { GET: vi.fn(), POST: vi.fn() },
  },
  ApiFailure: class extends Error {},
  parseApiError: () => ({ message: 'err' }),
}));

vi.mock('../src/features/matrices/access', () => ({
  matricesAccess: () => ({
    readMatrices: async () => matricesFixture,
    readMatrizVigente: async () => null,
  }),
}));

const sessionStore: Record<string, string> = {};

describe('matrices screens', () => {
  beforeEach(() => {
    reads.length = 0;
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => sessionStore[k] ?? null,
      setItem: (k: string, v: string) => { sessionStore[k] = v; },
      removeItem: (k: string) => { delete sessionStore[k]; },
    });
  });

  it('A: Nueva matriz muestra Seguir y tarjetas de arranque', () => {
    reads.push(catalogosOcMatricesFixture);
    reads.push(plantillasConCambiosFixture);
    reads.push(matricesFixture);
    const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/matrices/nueva'] }, createElement(MatrizNuevaScreen)));
    expect(html).toContain('Nueva matriz');
    expect(html).toContain('Seguir');
    expect(html).toContain('Desde cero');
  });

  it('B: Editor muestra Publicar y leyenda de candados', () => {
    saveMatrizDraft({
      clienteId: 'c', locacionId: 'l', tipoServicioId: 'ts', modo: 'cero',
      lineas: [{ requisito_definicion_id: 'r1', nombre: 'Apto', tipo_sujeto_aplicable: 'persona', categoria: 'documento', incluido: true, clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true }],
      vigenteDesde: '2026-09-18', fuente: 'test', archivoDeRespaldo: '',
    });
    reads.push({ items: [{ requisito_definicion_id: 'r1', nombre: 'Apto', tipo_sujeto_aplicable: 'persona', categoria: 'documento', activa: true }] });
    const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/matrices/editor'] }, createElement(MatrizEditorScreen)));
    expect(html).toContain('Publicar');
    expect(html).toContain('Bloqueante');
    expect(html).toContain('Apto');
  });

  it('C: Actualización de plantilla lista cambios y Traer N cambios', () => {
    reads.push(plantillasConCambiosFixture);
    const html = renderToStaticMarkup(createElement(
      MemoryRouter,
      { initialEntries: ['/matrices/plantilla/mg-1/mv-copia-1'] },
      createElement(PlantillaActualizacionScreen),
    ));
    expect(html).toContain('Altura');
    expect(html).toContain('Traer 1 cambios');
    expect(html).toContain('Ahora no');
  });

  it('D: Backlog OC sin matriz muestra pastilla y Crear matriz', () => {
    reads.push(catalogosOcMatricesFixture);
    reads.push(backlogSinMatrizFixture);
    const html = renderToStaticMarkup(createElement(
      MemoryRouter,
      { initialEntries: ['/backlog-oc'] },
      createElement(BacklogOcScreen, { roles: ['responsable_legajos'] }),
    ));
    expect(html).toContain('Sin matriz');
    expect(html).toContain('Crear matriz');
    expect(html).toContain('cliente_id=c-norte');
  });

  it('Listado matrices: botón Nueva matriz para responsable', () => {
    reads.push(catalogosOcMatricesFixture);
    reads.push(plantillasConCambiosFixture);
    reads.push(matricesFixture);
    const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/matrices'] }, createElement(MatricesScreen, {})));
    expect(html).toContain('Nueva matriz');
    expect(html).toContain('Ver cambios');
  });
});
