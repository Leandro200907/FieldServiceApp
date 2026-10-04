import { describe, expect, it } from 'vitest';
import { ejecutarAccionBandejaExitosa } from '../src/features/propuestas/bandejaAccionExitosa';

describe('ejecutarAccionBandejaExitosa', () => {
  it('registra el aviso antes de avanzar al siguiente ítem (confirmar y seguir)', async () => {
    const order: string[] = [];
    ejecutarAccionBandejaExitosa({
      mensaje: '✓ Licencia de conducir de Lucía Fernández confirmada',
      setAviso: () => { order.push('aviso'); },
      refresh: () => { order.push('refresh'); },
      avanzar: () => { order.push('avanzar'); },
    });
    expect(order).toEqual(['aviso', 'refresh']);
    await Promise.resolve();
    expect(order).toEqual(['aviso', 'refresh', 'avanzar']);
  });

  it('no avanza si no hay siguiente ítem', () => {
    let aviso: string | null = null;
    ejecutarAccionBandejaExitosa({
      mensaje: 'Propuesta de Juan Pérez rechazada',
      setAviso: m => { aviso = m; },
      refresh: () => {},
    });
    expect(aviso).toBe('Propuesta de Juan Pérez rechazada');
  });
});
