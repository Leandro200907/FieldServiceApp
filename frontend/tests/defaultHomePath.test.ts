import { describe, expect, it } from 'vitest';
import { defaultHomePath } from '../src/app/returnTo';

describe('defaultHomePath', () => {
  it('lleva al inicio de cada rol', () => {
    expect(defaultHomePath(['responsable_legajos'])).toBe('/propuestas');
    expect(defaultHomePath(['tecnico'])).toBe('/mi-legajo');
    expect(defaultHomePath(['configuracion'])).toBe('/configuracion');
    expect(defaultHomePath(['supervisor'])).toBe('/radar-documental');
  });

  it('prioriza configuración si hay varios roles', () => {
    expect(defaultHomePath(['tecnico', 'configuracion'])).toBe('/configuracion');
    expect(defaultHomePath(['responsable_legajos', 'supervisor'])).toBe('/propuestas');
  });
});
