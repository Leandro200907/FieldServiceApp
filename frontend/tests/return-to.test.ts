import { describe, expect, it } from 'vitest';
import { isInternalReturn, resolvePostLoginPath } from '../src/app/returnTo';

describe('returnTo post-login', () => {
  it('acepta rutas internas con detalle de legajo', () => {
    expect(isInternalReturn('/legajos/persona_patagonia_demo_t1')).toBe(true);
    const dest = resolvePostLoginPath('/legajos/persona_patagonia_demo_t1', ['responsable_legajos']);
    expect(dest).toBe('/legajos/persona_patagonia_demo_t1');
  });

  it('rechaza open redirect', () => {
    expect(isInternalReturn('//evil.example')).toBe(false);
  });
});
