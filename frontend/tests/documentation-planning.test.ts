import { describe, expect, it } from 'vitest';
import { deriveVisualState } from '../src/features/documentation-planning/contracts';
import { temporaryMockAccess } from '../src/features/documentation-planning/temporaryMockAccess';

describe('documentary radar contract', () => {
  it('keeps the general calendar independent from OC applicability', async () => {
    const calendar = await temporaryMockAccess.readCalendar({ from: '2026-09-01', to: '2026-10-31' });
    for (const item of calendar.items) {
      expect(item).not.toHaveProperty('obligatorio');
      expect(item).not.toHaveProperty('oc_id');
    }
  });

  it('derives only calendar presentation states', async () => {
    const calendar = await temporaryMockAccess.readCalendar({ from: '2026-09-01', to: '2026-10-31' });
    expect(new Set(calendar.items.map(deriveVisualState))).toEqual(new Set(['declarada', 'verificada', 'vencida']));
  });

  it('shows every OC by default and covers the four radar states', async () => {
    const radar = await temporaryMockAccess.readRadarBacklog({});
    expect(radar.items).toHaveLength(radar.total);
    expect(new Set(radar.items.map(row => row.oc_id)).size).toBe(radar.items.length);
    expect(new Set(radar.items.map(row => row.estado_documental))).toEqual(new Set([
      'sin_alertas_documentales', 'con_alertas_documentales', 'informacion_incompleta', 'sin_matriz',
    ]));
  });

  it('does not expose assignment, candidates or documentary capacity', async () => {
    const radar = await temporaryMockAccess.readRadarBacklog({});
    for (const row of radar.items) {
      expect(row).not.toHaveProperty('candidatos');
      expect(row).not.toHaveProperty('origen_calculo');
      expect(row).not.toHaveProperty('capacidad_documental_potencial_hoy');
      expect(row).not.toHaveProperty('recursos_asignados');
    }
  });

  it('filters without changing the informational model', async () => {
    const radar = await temporaryMockAccess.readRadarBacklog({ estado: ['con_alertas_documentales'], q: '45000221' });
    expect(radar.items).toHaveLength(1);
    expect(radar.items[0].estado_documental).toBe('con_alertas_documentales');
  });

  it('opens OC and legajo details through radar endpoints', async () => {
    const radar = await temporaryMockAccess.readRadarBacklog({ estado: ['con_alertas_documentales'] });
    const detail = await temporaryMockAccess.readRadarOc({ ocId: radar.items[0].oc_id });
    expect(detail.estado_documental).toBe('con_alertas_documentales');
    const legajo = await temporaryMockAccess.readRadarLegajo({ ocId: radar.items[0].oc_id, sujetoId: 'persona-marina' });
    expect(legajo.legajo.sujeto_id).toBe('persona-marina');
  });
});


