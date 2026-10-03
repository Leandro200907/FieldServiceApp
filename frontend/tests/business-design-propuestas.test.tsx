import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { BusinessDesign } from '../src/app/BusinessDesign';
import type { Page } from '../src/app/capabilities';

vi.mock('../src/features/propuestas/PropuestasScreen', () => ({
  PropuestasScreen: (props: { accessOverride?: unknown; readOnly?: boolean }) =>
    createElement('div', {
      'data-mock': String(Boolean(props.accessOverride)),
      'data-readonly': String(Boolean(props.readOnly)),
    }),
}));

const propuestasPage: Page = {
  id: 'propuestas',
  label: 'Propuestas',
  description: 'Revisión documental',
  roles: ['responsable_legajos'],
  gaps: ['G-03'],
};

describe('BusinessDesign · propuestas en workspace', () => {
  it('no inyecta mock ni solo lectura fuera del catálogo de diseño', () => {
    const html = renderToStaticMarkup(createElement(BusinessDesign, { page: propuestasPage }));
    expect(html).toContain('data-mock="false"');
    expect(html).toContain('data-readonly="false"');
  });
});
