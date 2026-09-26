import { featureFlags } from '../../app/flags';
import type { MiLegajoAccess } from './contracts';
import { realMiLegajoAccess } from './realMiLegajoAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real (mismo patrón que documentation-planning/access.ts).
// `featureFlags.technicianCompositeView` estaba definido pero nunca conectado a nada — este
// es el primer lugar que lo lee de verdad.
export function miLegajoAccess(): MiLegajoAccess {
  return featureFlags.technicianCompositeView ? realMiLegajoAccess : temporaryMockAccess;
}

export function isMiLegajoIntegrated(): boolean {
  return featureFlags.technicianCompositeView;
}
