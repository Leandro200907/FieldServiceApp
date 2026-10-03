import { describe, expect, it } from 'vitest';
import { buildOperadoraFilterOpts, erroresDesdeImportacion, etiquetaFilaImportacion, toggleSearchListParam } from '../src/features/vencimientos/importacionUi';

describe('importacionUi', () => {
  it('etiquetaFilaImportacion distingue fila sin número', () => {
    expect(etiquetaFilaImportacion(6)).toBe('Fila 6');
    expect(etiquetaFilaImportacion(null)).toBe('Fila sin número');
  });

  it('erroresDesdeImportacion extrae detalles de planilla_invalida', () => {
    const errores = erroresDesdeImportacion({
      message: 'La planilla tiene filas con errores de formato',
      code: 'planilla_invalida',
      status: 422,
      requestId: 'x',
      referenceSource: 'server',
      details: { errores: [{ fila: null, mensaje: 'Celda inválida' }, { fila: 7, mensaje: 'Fecha inválida' }] },
    });
    expect(errores).toEqual([
      { fila: null, mensaje: 'Celda inválida' },
      { fila: 7, mensaje: 'Fecha inválida' },
    ]);
  });

  it('toggleSearchListParam acumula YPF y Vista en la query', () => {
    let params = new URLSearchParams();
    params = toggleSearchListParam(params, 'operadora_id', 'ypf');
    params = toggleSearchListParam(params, 'operadora_id', 'vista');
    expect(params.getAll('operadora_id')).toEqual(['ypf', 'vista']);
  });

  it('buildOperadoraFilterOpts mantiene seleccionadas aunque no estén en resultados filtrados', () => {
    const opts = buildOperadoraFilterOpts(
      [{ operadora_id: 'ypf', nombre: 'YPF' }, { operadora_id: 'vista', nombre: 'Vista' }],
      ['ypf', 'vista'],
      new Map(),
    );
    expect(opts.map(o => o.nombre)).toEqual(['Vista', 'YPF']);
  });
});
