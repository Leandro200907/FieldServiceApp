import { describe, expect, it } from 'vitest';
import { ordenarOcsAfectadas, resumenOcsAfectadas } from '../src/ui/ocsAfectadasPresentacion';

const TZ = 'America/Argentina/Buenos_Aires';

describe('ocsAfectadasPresentacion', () => {
  it('ordena en curso primero y luego por fecha de inicio', () => {
    const ocs = [
      { clave_origen: 'OC-REP', vigencia_desde: '2026-10-16', vigencia_hasta: '2026-10-20' },
      { clave_origen: 'OC-CURSO', vigencia_desde: '2026-09-28', vigencia_hasta: '2026-11-02' },
      { clave_origen: 'OC-FUT', vigencia_desde: '2026-11-10', vigencia_hasta: '2026-11-15' },
    ];
    const ordenadas = ordenarOcsAfectadas(ocs, '2026-10-03');
    expect(ordenadas.map(o => o.clave_origen)).toEqual(['OC-CURSO', 'OC-REP', 'OC-FUT']);
  });

  it('resume como enlace “Afecta N OC” y detalle completo en título', () => {
    const ocs = [
      { clave_origen: 'OC-patagonia-demo-CURSO', vigencia_desde: '2026-09-28', vigencia_hasta: '2026-11-02' },
      { clave_origen: 'OC-patagonia-demo-REP', vigencia_desde: '2026-10-16', vigencia_hasta: '2026-10-22' },
      { clave_origen: 'OC-patagonia-demo-3', vigencia_desde: '2026-11-01', vigencia_hasta: '2026-11-05' },
      { clave_origen: 'OC-patagonia-demo-4', vigencia_desde: '2026-11-08', vigencia_hasta: '2026-11-12' },
    ];
    const { resumen, tituloCompleto } = resumenOcsAfectadas(ocs, '2026-10-03', TZ)!;
    expect(resumen).toBe('Afecta 4 OCs');
    expect(tituloCompleto).toContain('OC-patagonia-demo-CURSO (en curso)');
    expect(tituloCompleto.split(', ').length).toBe(4);
  });
});
