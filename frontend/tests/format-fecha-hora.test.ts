import { describe, expect, it } from 'vitest';
import { formatFechaHora } from '../src/ui/fechas';

describe('formatFechaHora', () => {
  it('formatea en es-AR con hora', () => {
    const out = formatFechaHora('2026-10-03T15:30:00Z', 'America/Argentina/Buenos_Aires');
    expect(out).toMatch(/\d{2}\/\d{2}\/2026/);
    expect(out).toMatch(/\d{2}:\d{2}/);
    expect(out).not.toMatch(/T/);
  });
});
