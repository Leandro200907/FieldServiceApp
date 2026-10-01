import { describe, expect, it } from 'vitest';
import { formatFecha } from '../src/features/documentation-planning/dates';
import { lineasDisponibilidad, resumenDocumental, textoAlertaCierta, textoHistorial, vigenciaReprogramacion } from '../src/features/documentation-planning/ocDetail';

const TZ = 'America/Argentina/Buenos_Aires';

describe('detalle de OC', () => {
  it('reprograma con las fechas de la OC si el usuario no las toca, o solo la que cambió', () => {
    const oc = { vigencia_desde: '2026-10-01', vigencia_hasta: '2026-11-30' };
    expect(vigenciaReprogramacion({ desde: '', hasta: '' }, oc)).toEqual({
      vigencia_desde: '2026-10-01',
      vigencia_hasta: '2026-11-30',
    });
    expect(vigenciaReprogramacion({ desde: '', hasta: '2026-12-15' }, oc)).toEqual({
      vigencia_desde: '2026-10-01',
      vigencia_hasta: '2026-12-15',
    });
  });

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

  it('resume alertas e impacto en texto, nunca booleanos', () => {
    const r = resumenDocumental({
      tiene_alertas: true,
      alertas_ciertas: [{ codigo: 'tipo_sin_habilitados', mensaje: 'x', tipo_sujeto: 'persona', tramos: [{ desde: '2026-11-19', hasta: '2026-11-25' }] }],
      impacto_por_tipo: [{ tipo_sujeto: 'persona', dias_sin_habilitados: 7 }],
    }, TZ);
    expect(r.alertas.join(' ')).not.toMatch(/true|false/);
    expect(r.impacto[0]).toBe('Personas: 7 días');
    expect(resumenDocumental({ tiene_alertas: false, alertas_ciertas: [], impacto_por_tipo: [] }, TZ).alertas).toEqual(['Sin alertas ciertas']);
  });

  it('formatea el historial sin ISO crudo', () => {
    expect(textoHistorial({ fecha: '2026-11-19T15:30:00+00:00', origen: 'reprogramacion', motivo: 'pedido del cliente' }, TZ))
      .toMatch(/19\/11\/2026 · reprogramacion · pedido del cliente/);
    expect(formatFecha('2026-11-19', TZ)).toBe('19/11/2026');
    expect(formatFecha('2026-11-19T15:30:00Z', TZ)).not.toMatch(/T/);
    expect(formatFecha('2026-11-19T15:30:00Z', TZ)).not.toMatch(/2026-11-19/);
  });
});
