import { describe, expect, it } from 'vitest';
import { observacionFila } from '../src/features/legajos/legajoFichaObservacion';

describe('E-105 observación en ficha legajo', () => {
  it('con rechazo de operadora muestra solo ese texto (sin guión del backend)', () => {
    expect(
      observacionFila({
        observacion_ficha: '—',
        observacion_operadora: 'Rechazado por Vista',
      }),
    ).toBe('Rechazado por Vista');
  });

  it('sin observaciones muestra guión', () => {
    expect(observacionFila({ observacion_ficha: '—' })).toBe('—');
    expect(observacionFila({})).toBe('—');
  });

  it('combina motivo de ficha con no exigido cuando no hay operadora', () => {
    expect(
      observacionFila({
        observacion_ficha: 'Archivo en verificación técnica',
        no_exigido_backlog: true,
      }),
    ).toBe('Archivo en verificación técnica · No exigido por OC actuales');
  });
});
