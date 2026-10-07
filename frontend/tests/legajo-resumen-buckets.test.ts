import { describe, expect, it } from 'vitest';
import {
  conteosTarjetasExigidos,
  pendientesRevisionDesdeResumen,
  proximoVencimientoDesdeResumen,
  resumenExigidosTexto,
} from '../src/features/legajos/legajoResumen';

describe('resumenExigidosTexto (E-96)', () => {
  it('Lucía: 1 sin documento', () => {
    expect(resumenExigidosTexto({ exigidos_sin_documento: 1, exigidos_vencidos: 0, exigidos_por_vencer: 0 })).toBe(
      '1 sin documento',
    );
  });

  it('María: sin pendientes de calendario ni faltantes', () => {
    expect(resumenExigidosTexto({ exigidos_sin_documento: 0, exigidos_vencidos: 0, exigidos_por_vencer: 0 })).toBe(
      'Sin pendientes',
    );
  });
});

describe('resumen legajo desde API (E-101)', () => {
  it('tarjetas y pendientes sin recalcular en el front', () => {
    const resumen = {
      exigidos_vencidos: 1,
      exigidos_por_vencer: 2,
      exigidos_vigentes: 3,
      exigidos_sin_documento: 0,
      pendientes_revision: 1,
      proximo_vencimiento: '2026-12-01',
    };
    expect(conteosTarjetasExigidos(resumen)).toEqual({
      vencidos: 1,
      por_vencer: 2,
      vigentes: 3,
      sin_documento: 0,
    });
    expect(pendientesRevisionDesdeResumen(resumen)).toBe(1);
    expect(proximoVencimientoDesdeResumen(resumen)).toBe('2026-12-01');
  });
});
