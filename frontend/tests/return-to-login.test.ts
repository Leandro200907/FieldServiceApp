import { describe, expect, it } from 'vitest';
import { isInternalReturn, loginPathWithReturn } from '../src/app/returnTo';

describe('return-to login', () => {
  it('acepta rutas internas con query', () => {
    expect(isInternalReturn('/vencimientos?operadora_id=ypf&operadora_id=vista')).toBe(true);
  });

  it('rechaza login y URLs externas', () => {
    expect(isInternalReturn('/login')).toBe(false);
    expect(isInternalReturn('//evil.example')).toBe(false);
    expect(isInternalReturn('https://evil.example/x')).toBe(false);
  });

  it('loginPathWithReturn codifica la ruta original', () => {
    expect(loginPathWithReturn('/vencimientos', '?operadora_id=ypf')).toBe('/login?return=%2Fvencimientos%3Foperadora_id%3Dypf');
  });
});
