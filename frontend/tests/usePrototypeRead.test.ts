import { describe, expect, it } from 'vitest';
import { beginReload, esCargaInicial } from '../src/hooks/usePrototypeRead';

describe('usePrototypeRead — recarga sin vaciar', () => {
  it('conserva los datos previos al volver a consultar', () => {
    const next = beginReload({ data: { total: 3 }, loading: false });
    expect(next.data).toEqual({ total: 3 });
    expect(next.loading).toBe(true);
    expect(next.error).toBeUndefined();
  });

  it('la carga a pantalla completa solo aplica si todavía no hay datos', () => {
    expect(esCargaInicial({ loading: true })).toBe(true);
    expect(esCargaInicial({ loading: true, data: { total: 3 } })).toBe(false);
    expect(esCargaInicial({ loading: false, data: { total: 3 } })).toBe(false);
  });
});
