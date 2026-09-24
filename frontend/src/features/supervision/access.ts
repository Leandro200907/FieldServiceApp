import { featureFlags } from '../../app/flags';
import type { SupervisionAccess } from './contracts';
import { realSupervisionAccess } from './realSupervisionAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real (mismo patrón que el resto de features).
export function supervisionAccess(): SupervisionAccess {
  return featureFlags.supervisionIntegration ? realSupervisionAccess : temporaryMockAccess;
}

export function isSupervisionIntegrated(): boolean {
  return featureFlags.supervisionIntegration;
}
