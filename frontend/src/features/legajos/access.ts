import { featureFlags } from '../../app/flags';
import type { LegajosAccess } from './contracts';
import { realLegajosAccess } from './realLegajosAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real (mismo patrón que mi-legajo/access.ts y
// vencimientos/access.ts).
export function legajosAccess(): LegajosAccess {
  return featureFlags.legajoLookupIntegration ? realLegajosAccess : temporaryMockAccess;
}

export function isLegajosIntegrated(): boolean {
  return featureFlags.legajoLookupIntegration;
}
