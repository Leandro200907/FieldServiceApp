import { describe, expect, it } from 'vitest';
import { ordenarErroresImportacion } from '../src/features/vencimientos/importacionUi';

describe('ordenarErroresImportacion', () => {
  it('ordena por número de fila', () => {
    const sorted = ordenarErroresImportacion([
      { fila: 12, mensaje: 'b' },
      { fila: 3, mensaje: 'a' },
      { fila: null, mensaje: 'sin fila' },
    ]);
    expect(sorted.map(e => e.fila)).toEqual([3, 12, null]);
  });
});
