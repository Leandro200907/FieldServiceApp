import { featureFlags } from '../../app/flags';
import type { PropuestasAccess } from './contracts';
import { realPropuestasAccess } from './realPropuestasAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real (mismo patrón que el resto de features).
export function propuestasAccess(): PropuestasAccess {
  return featureFlags.pendingProposalsIntegration ? realPropuestasAccess : temporaryMockAccess;
}

export function isPropuestasIntegrated(): boolean {
  return featureFlags.pendingProposalsIntegration;
}
