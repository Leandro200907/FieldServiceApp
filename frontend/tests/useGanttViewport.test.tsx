import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { useGanttViewport } from '../src/features/documentation-planning/useGanttViewport';

function Probe({ hoy }: { hoy: string }) {
  const g = useGanttViewport({ hoy, autoDesde: null, autoHasta: null });
  return createElement('span', { 'data-desde': g.vistaDesde, 'data-hasta': g.vistaHasta });
}

describe('useGanttViewport', () => {
  it('no rompe con hoy vacío (primer render antes del backend)', () => {
    const html = renderToStaticMarkup(createElement(Probe, { hoy: '' }));
    expect(html).toContain('data-desde=""');
    expect(html).toContain('data-hasta=""');
  });
});
