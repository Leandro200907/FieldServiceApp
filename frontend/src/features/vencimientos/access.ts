import { featureFlags } from '../../app/flags';
import type { VencimientosAccess } from './contracts';
import { realVencimientosAccess } from './realVencimientosAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real (mismo patrón que documentation-planning/access.ts
// y mi-legajo/access.ts).
export function vencimientosAccess(): VencimientosAccess {
  return featureFlags.expirationsBoardIntegration ? realVencimientosAccess : temporaryMockAccess;
}

export function isVencimientosIntegrated(): boolean {
  return featureFlags.expirationsBoardIntegration;
}
