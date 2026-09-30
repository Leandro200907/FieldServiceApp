import { describe, expect, it } from 'vitest';
import { formatFecha } from '../src/features/documentation-planning/dates';
import { lineasDisponibilidad, textoAlertaCierta, textoHistorial } from '../src/features/documentation-planning/ocDetail';

const TZ = 'America/Argentina/Buenos_Aires';

describe('detalle de OC', () => {
  it('lista nombres de habilitados, caídas y no habilitados', () => {
    const lineas = lineasDisponibilidad({
      tipo_sujeto: 'persona',
      etiqueta: 'Técnicos',
      estado: 'ok',
      texto: 'Técnicos: 1 habilitados',
      habilitados_toda_ventana: [{ nombre: 'Ana' }],
      se_cae_en_ventana: [{ nombre: 'Luis', fecha: '2026-11-18', requisito: 'Apto médico' }],
      no_habilitados: [{ nombre: 'Marta' }],
    }, TZ);
    expect(lineas[0]).toContain('Ana');
    expect(lineas[1]).toMatch(/se cae el 18\/11\/2026 por Apto médico \(Luis\)/);
    expect(lineas[2]).toContain('Marta');
  });

  it('arma la alerta cierta con tramo e impacto en días', () => {
    const texto = textoAlertaCierta(
      {
        codigo: 'tipo_sin_habilitados',
        mensaje: 'Ningún legajo habilitado de tipo persona',
        tipo_sujeto: 'persona',
        tramos: [{ desde: '2026-11-19', hasta: '2026-11-25' }],
      },
      [{ tipo_sujeto: 'persona', dias_sin_habilitados: 7, tramos: [{ desde: '2026-11-19', hasta: '2026-11-25' }] }],
      TZ,
    );
    expect(texto).toBe('Personas: 7 días sin ningún habilitado, 19/11/2026 al 25/11/2026');
  });

  it('formatea el historial sin ISO crudo', () => {
    expect(textoHistorial({ fecha: '2026-11-19T15:30:00+00:00', origen: 'reprogramacion', motivo: 'pedido del cliente' }, TZ))
      .toMatch(/19\/11\/2026 · reprogramacion · pedido del cliente/);
    expect(formatFecha('2026-11-19', TZ)).toBe('19/11/2026');
  });
});
