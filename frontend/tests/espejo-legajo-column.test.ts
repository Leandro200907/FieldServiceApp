import { describe, expect, it } from 'vitest';
import { espejoLegajoLabel } from '../src/features/vencimientos/espejoLegajoLabel';

describe('E-26 espejo por operadora — columna Legajo', () => {
  it('muestra nombre y DNI para personas', () => {
    const texto = espejoLegajoLabel({
      tipo_sujeto: 'persona',
      nombre_apellido: 'María González',
      identificador_natural: '30.111.222',
      sujeto_id: 'suj-1',
    });
    expect(texto).toBe('María González · DNI 30.111.222');
    expect(texto).not.toBe('30.111.222');
  });
});
