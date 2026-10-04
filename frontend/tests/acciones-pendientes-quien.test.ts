import { describe, expect, it } from 'vitest';
import { lineaPersonaConDni } from '../src/features/legajos/legajoDisplay';

describe('E-26 acciones pendientes — columna Quién', () => {
  it('no muestra sujeto_id interno en la línea de persona', () => {
    const texto = lineaPersonaConDni({
      tipo_sujeto: 'persona',
      nombre_apellido: 'María González',
      identificador_natural: '30.111.222',
      sujeto_id: 'persona_patagonia_demo_t1',
    });
    expect(texto).toBe('María González · DNI 30.111.222');
    expect(texto).not.toContain('persona_patagonia_demo');
  });

  it('usa identificador natural para recursos no persona', () => {
    expect(lineaPersonaConDni({
      tipo_sujeto: 'vehiculo',
      nombre_apellido: null,
      identificador_natural: 'PA100DE',
      sujeto_id: 'vehiculo_patagonia_demo_1',
    })).toBe('PA100DE');
  });
});
