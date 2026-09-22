import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { addDays, dayPosition, todayIso } from '../src/features/documentation-planning/dates';

describe('todayIso — F-03: fecha local, nunca UTC', () => {
  const zonaOriginal = process.env.TZ;

  beforeEach(() => {
    process.env.TZ = 'America/Argentina/Buenos_Aires';
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    process.env.TZ = zonaOriginal;
  });

  it('a las 22:30 de Buenos Aires (01:30 UTC del día siguiente) sigue siendo el día LOCAL, no el de UTC', () => {
    // 2026-09-22T01:30:00Z = 2026-09-21T22:30:00-03:00 en Buenos Aires: todavía 21, no 22.
    vi.setSystemTime(new Date('2026-09-22T01:30:00Z'));
    expect(todayIso()).toBe('2026-09-21');
  });

  it('a las 10:00 de Buenos Aires (13:00 UTC), coincide con el día en ambos husos — caso de control', () => {
    vi.setSystemTime(new Date('2026-09-21T13:00:00Z'));
    expect(todayIso()).toBe('2026-09-21');
  });
});

describe('addDays', () => {
  it('suma días en UTC calendario, sin depender de la hora local', () => {
    expect(addDays('2026-09-21', 40)).toBe('2026-10-31');
    expect(addDays('2026-01-01', 1)).toBe('2026-01-02');
  });
});

describe('dayPosition — F-01: posición de una fecha dentro de [from, to], nunca fija', () => {
  it('el extremo `from` está en 0%, el extremo `to` en 100%', () => {
    expect(dayPosition('2026-09-01', '2026-09-01', '2026-09-11')).toBe(0);
    expect(dayPosition('2026-09-11', '2026-09-01', '2026-09-11')).toBe(100);
  });

  it('un punto a mitad de camino cae en 50%', () => {
    expect(dayPosition('2026-09-06', '2026-09-01', '2026-09-11')).toBe(50);
  });

  it('recorta a [0, 100] una fecha fuera del rango pedido', () => {
    expect(dayPosition('2026-08-01', '2026-09-01', '2026-09-11')).toBe(0);
    expect(dayPosition('2026-10-01', '2026-09-01', '2026-09-11')).toBe(100);
  });

  it('regresión directa de F-01: con `from` igual a "hoy" (como siempre lo arma la pantalla), "hoy" cae en 0%, nunca en un 40% fijo', () => {
    const hoy = '2026-09-21';
    const hasta = addDays(hoy, 40);
    expect(dayPosition(hoy, hoy, hasta)).toBe(0);
  });
});
