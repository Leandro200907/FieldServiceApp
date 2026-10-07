import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MatricesScreen } from '../src/features/matrices/MatricesScreen';
import { MatrizEditorScreen } from '../src/features/matrices/MatrizEditorScreen';
import { matricesFixture } from './fixtures/reglaUnicaBackend';
import { saveMatrizDraft } from '../src/features/matrices/matrizDraft';

const reads: unknown[] = [];
let mockRoles = ['tecnico'];

vi.mock('../src/hooks/usePrototypeRead', () => ({
  usePrototypeRead: () => ({ data: reads.shift(), loading: false, error: null }),
  esCargaInicial: () => false,
}));

vi.mock('../src/api', () => ({
  session: {
    getSnapshot: () => ({ identity: { roles: mockRoles, zona_horaria: 'America/Argentina/Buenos_Aires' } }),
    client: { GET: vi.fn() },
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

describe('matrices roles', () => {
  beforeEach(() => {
    reads.length = 0;
    mockRoles = ['tecnico'];
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => sessionStore[k] ?? null,
      setItem: (k: string, v: string) => { sessionStore[k] = v; },
      removeItem: (k: string) => { delete sessionStore[k]; },
    });
  });

  it('10a: técnico no ve Nueva matriz', () => {
    reads.push({ operadoras: [] });
    reads.push(null);
    reads.push(matricesFixture);
    const html = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/matrices'] }, createElement(MatricesScreen, {})));
    expect(html).not.toContain('Nueva matriz');
  });

  it('10b: supervisor no ve Nueva matriz ni Publicar en editor', () => {
    mockRoles = ['supervisor'];
    reads.push({ operadoras: [] });
    reads.push(null);
    reads.push(matricesFixture);
    const list = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/matrices'] }, createElement(MatricesScreen, {})));
    expect(list).not.toContain('Nueva matriz');
    saveMatrizDraft({
      clienteId: 'c', locacionId: 'l', tipoServicioId: 'ts', modo: 'cero',
      lineas: [{ requisito_definicion_id: 'r1', nombre: 'Apto', tipo_sujeto_aplicable: 'persona', categoria: 'documento', incluido: true, clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true }],
      vigenteDesde: '2026-09-18', fuente: 'test', archivoDeRespaldo: '',
    });
    reads.push({ items: [{ requisito_definicion_id: 'r1', nombre: 'Apto', tipo_sujeto_aplicable: 'persona', categoria: 'documento', activa: true }] });
    const editor = renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: ['/matrices/editor'] }, createElement(MatrizEditorScreen)));
    expect(editor).not.toContain('Publicar');
  });
});
