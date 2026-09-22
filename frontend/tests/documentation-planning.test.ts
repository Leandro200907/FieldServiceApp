import { describe, expect, it } from 'vitest';
import { deriveVisualState } from '../src/features/documentation-planning/contracts';
import { temporaryMockAccess } from '../src/features/documentation-planning/temporaryMockAccess';

describe('temporary documentary planning mock (real contract shape)', () => {
  it('never carries a matriz/OC applicability field — calendario_vigencias cannot know that (docs/PROYECCION_DOCUMENTAL.md §2.1)', async () => {
    const calendar = await temporaryMockAccess.readCalendar({ from: '2026-09-01', to: '2026-10-31' });
    expect(calendar.advertencia).toMatch(/No garantiza disponibilidad/);
    for (const item of calendar.items) {
      expect(item).not.toHaveProperty('applicability');
      expect(item).not.toHaveProperty('obligatorio');
    }
  });

  it('derives declarada/vencida/verificada without ever needing proxima_a_vencer or sin_evidencia', async () => {
    const calendar = await temporaryMockAccess.readCalendar({ from: '2026-09-01', to: '2026-10-31' });
    const states = new Set(calendar.items.map(deriveVisualState));
    expect(states).toEqual(new Set(['declarada', 'verificada', 'vencida']));
  });

  it('contains one unique row per OC and covers all 6 closed states', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({});
    expect(new Set(projection.items.map(row => row.commitment_id)).size).toBe(projection.items.length);
    expect(new Set(projection.items.map(row => row.estado))).toEqual(new Set([
      'sin_riesgos_detectados', 'riesgo_documental', 'bloqueo_confirmado', 'pendiente_de_planificacion', 'sin_matriz', 'requiere_revision',
    ]));
    expect(projection.advertencia).toBe('Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa.');
  });

  it('labels counts as potential documentary capacity, keyed by type, never as availableResources', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({});
    expect(projection.items.every(row => Object.hasOwn(row, 'capacidad_documental_potencial_hoy'))).toBe(true);
    expect(JSON.stringify(projection)).not.toContain('availableResources');
  });

  it('never represents "not computed" as zero — sin_matriz/pendiente_de_planificacion get an empty object, not zeroed keys', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({});
    for (const row of projection.items.filter(row => ['sin_matriz', 'pendiente_de_planificacion'].includes(row.estado))) {
      expect(row.capacidad_documental_potencial_hoy).toEqual({});
    }
  });

  it('always carries origen_calculo as one of the two real values, never the invented evaluationBasis vocabulary', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({});
    for (const row of projection.items) {
      expect(['ultima_decision_visible', 'candidatos_del_alcance']).toContain(row.origen_calculo);
    }
  });

  it('exposes a real-shaped projection detail for a backlog row, matching its own summary state', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({});
    const row = projection.items.find(item => item.estado === 'riesgo_documental');
    expect(row).toBeTruthy();
    const detail = await temporaryMockAccess.readProjectionDetail({ commitmentId: row!.commitment_id });
    expect(detail.estado).toBe(row!.estado);
    expect(detail.commitment_id).toBe(row!.commitment_id);
  });

  it('matriz is null only for sin_matriz — pendiente_de_planificacion keeps it populated', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({});
    const sinMatriz = projection.items.find(item => item.estado === 'sin_matriz')!;
    const pendiente = projection.items.find(item => item.estado === 'pendiente_de_planificacion')!;
    expect((await temporaryMockAccess.readProjectionDetail({ commitmentId: sinMatriz.commitment_id })).matriz).toBeNull();
    expect((await temporaryMockAccess.readProjectionDetail({ commitmentId: pendiente.commitment_id })).matriz).not.toBeNull();
  });

  it('rejects an unknown reference for the detail endpoint', async () => {
    await expect(temporaryMockAccess.readProjectionDetail({ commitmentId: 'OC-NO-EXISTE' })).rejects.toThrow(/no contiene el detalle/);
  });
});
