import { describe, expect, it } from 'vitest';
import { formatDaysToExpiry } from '../src/ui/formatDaysToExpiry';

describe('formatDaysToExpiry', () => {
  it('usa singular para un día', () => {
    expect(formatDaysToExpiry(1)).toBe('vence en 1 día');
    expect(formatDaysToExpiry(-1)).toBe('venció hace 1 día');
  });

  it('usa plural para cero y varios días', () => {
    expect(formatDaysToExpiry(0)).toBe('vence en 0 días');
    expect(formatDaysToExpiry(20)).toBe('vence en 20 días');
    expect(formatDaysToExpiry(-2)).toBe('venció hace 2 días');
  });
});

