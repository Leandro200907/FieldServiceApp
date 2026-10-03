import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { addDays, axisTicks, clipSegment, dayPosition, formatTick, todayIso } from '../src/features/documentation-planning/dates';

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

describe('clipSegment — recorte al rango visible', () => {
  it('devuelve null si el tramo queda fuera del gráfico', () => {
    expect(clipSegment('2026-08-01', '2026-08-15', '2026-09-01', '2026-09-30')).toBeNull();
    expect(clipSegment('2026-10-01', '2026-10-15', '2026-09-01', '2026-09-30')).toBeNull();
  });

  it('recorta el tramo que se sale por los extremos y no produce overflow', () => {
    const clipped = clipSegment('2026-08-20', '2026-09-10', '2026-09-01', '2026-09-11');
    expect(clipped).not.toBeNull();
    expect(clipped!.left).toBe(0);
    expect(clipped!.width).toBeLessThanOrEqual(100);
    expect(clipped!.left + clipped!.width).toBeLessThanOrEqual(100);
  });
});

describe('formatTick', () => {
  it('pone el año solo cuando cambia respecto del tick anterior', () => {
    expect(formatTick('2026-12-20', null, 'UTC')).not.toMatch(/2026/);
    expect(formatTick('2027-01-15', '2026-12-20', 'UTC')).toMatch(/2027/);
    expect(formatTick('2027-02-01', '2027-01-15', 'UTC')).not.toMatch(/2027/);
  });
});

describe('axisTicks', () => {
  it('queda dentro del rango elegido y no genera ticks demasiado juntos', () => {
    const ticks = axisTicks('2026-10-01', '2026-12-30');
    expect(ticks[0]).toBe('2026-10-01');
    expect(ticks.every(t => t >= '2026-10-01' && t <= '2026-12-30')).toBe(true);
    for (let i = 1; i < ticks.length; i++) {
      expect(dayPosition(ticks[i], '2026-10-01', '2026-12-30') - dayPosition(ticks[i - 1], '2026-10-01', '2026-12-30')).toBeGreaterThanOrEqual(12);
    }
  });

  it('en un rango de 90 días no se estira a años de vigencia ajenos', () => {
    const ticks = axisTicks('2026-10-01', addDays('2026-10-01', 90));
    expect(ticks[0] >= '2026-10-01').toBe(true);
    expect(ticks[ticks.length - 1] <= addDays('2026-10-01', 90)).toBe(true);
    expect(ticks.some(t => t.startsWith('2021') || t.startsWith('2031'))).toBe(false);
  });
});
