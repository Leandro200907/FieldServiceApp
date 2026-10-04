import { describe, expect, it } from 'vitest';
import { defaultHomePath, resolvePostLoginPath } from '../src/app/returnTo';

describe('resolvePostLoginPath', () => {
  it('respeta return solo si el rol puede abrir la pantalla', () => {
    expect(resolvePostLoginPath('/configuracion', ['responsable_legajos'])).toBe('/propuestas');
    expect(resolvePostLoginPath('/legajos', ['tecnico'])).toBe('/mi-legajo');
    expect(resolvePostLoginPath('/legajos', ['responsable_legajos'])).toBe('/legajos');
  });

  it('usa return con query cuando el rol tiene permiso', () => {
    expect(resolvePostLoginPath('/vencimientos?operadora_id=ypf', ['responsable_legajos']))
      .toBe('/vencimientos?operadora_id=ypf');
  });

  it('sin return usa la misma pantalla de inicio que el logo', () => {
    expect(resolvePostLoginPath(null, ['responsable_legajos', 'supervisor'])).toBe(defaultHomePath(['responsable_legajos', 'supervisor']));
  });
});
