import { describe, expect, it } from 'vitest';
import { textoAccionSugerida, textoEfectoAccion } from '../src/features/documentation-planning/copy';

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

  it('formatea la fecha de la acción en la zona del tenant, sin ISO', () => {
    expect(textoAccionSugerida('Renovar antes del', '2026-11-13', 'America/Argentina/Buenos_Aires'))
      .toBe('Renovar antes del 13/11/2026');
    expect(textoAccionSugerida('Revisar y confirmar la evidencia', null, 'America/Argentina/Buenos_Aires'))
      .toBe('Revisar y confirmar la evidencia');
  });
});
