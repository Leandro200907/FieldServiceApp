import { describe, expect, it } from 'vitest';
import { textoEfectoAccion } from '../src/features/documentation-planning/copy';

describe('copy de acciones pendientes', () => {
  it('dice disponibilidad documental, no cobertura', () => {
    expect(textoEfectoAccion('deja un período sin cobertura documental')).toBe(
      'deja un período sin disponibilidad documental',
    );
    expect(textoEfectoAccion('no tiene cobertura documental al inicio del período')).toBe(
      'no tiene disponibilidad documental al inicio del período',
    );
    expect(textoEfectoAccion('Renovación de apto médico')).toBe('Renovación de apto médico');
  });
});
