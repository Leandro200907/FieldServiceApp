import { describe, expect, it } from 'vitest';
import { TEMPORARY_CONTRACT_SOURCE } from '../src/features/documentation-planning/contracts';
import { temporaryMockAccess } from '../src/features/documentation-planning/temporaryMockAccess';

describe('temporary documentary planning contracts', () => {
  it('keeps non-contextual evidence from becoming an asserted obligation', async () => {
    const calendar = await temporaryMockAccess.readCalendar({ scope: 'responsible', from: '2026-09-01', to: '2026-10-31' });
    expect(calendar.source).toBe(TEMPORARY_CONTRACT_SOURCE);
    const withoutContext = calendar.intervals.filter(item => item.applicability.kind === 'none');
    expect(withoutContext.length).toBeGreaterThan(0);
    for (const item of withoutContext) expect(item.applicability.label).toMatch(/Sin matriz u OC/);
  });

  it('contains one unique row per OC and all requested visual states', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({ scope: 'responsible', from: '2026-09-21', to: '2026-10-31' });
    expect(new Set(projection.rows.map(row => row.ocLabel)).size).toBe(projection.rows.length);
    expect(new Set(projection.rows.map(row => row.state))).toEqual(new Set([
      'sin_riesgos_detectados', 'riesgo_documental', 'bloqueo_confirmado', 'pendiente_planificacion', 'sin_matriz', 'requiere_revision',
    ]));
    expect(projection.warning).toBe('No garantiza disponibilidad ni asignación operativa');
  });

  it('labels counts as potential documentary capacity and never as availability in the contract', async () => {
    const projection = await temporaryMockAccess.readBacklogProjection({ scope: 'supervisor', from: '2026-09-21', to: '2026-10-31' });
    expect(projection.rows.every(row => Object.hasOwn(row, 'potentialCapacity'))).toBe(true);
    expect(JSON.stringify(projection)).not.toContain('availableResources');
  });

  it('applies the same role scope to calendar detail', async () => {
    await expect(temporaryMockAccess.readExplanation({ scope: 'technician', reference: 'CAL-EMP-01' })).rejects.toThrow(/fuera del alcance/);
    await expect(temporaryMockAccess.readExplanation({ scope: 'technician', reference: 'BACK-01' })).rejects.toThrow(/no está disponible/);
  });
});

it('limits the technician prototype to one own person and denies another person detail', async () => {
  const data = await temporaryMockAccess.readCalendar({ scope: 'technician', from: '2026-09-01', to: '2026-10-31' });
  expect(data.intervals.filter(item => item.subjectKind === 'persona')).toHaveLength(1);
  await expect(temporaryMockAccess.readExplanation({ scope: 'technician', reference: 'CAL-PER-02' })).rejects.toThrow(/fuera del alcance/);
});
it('does not present unknown capacity as zero', async () => {
  const data = await temporaryMockAccess.readBacklogProjection({ scope: 'responsible', from: '2026-09-01', to: '2026-10-31' });
  for (const row of data.rows.filter(row => ['sin_matriz', 'pendiente_planificacion'].includes(row.state))) {
    expect(row.potentialCapacity).toBeNull();
  }
});
