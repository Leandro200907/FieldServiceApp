import { featureFlags } from '../../app/flags';
import type { MatricesAccess } from './contracts';
import { realMatricesAccess } from './realMatricesAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real (mismo patrón que el resto de features).
export function matricesAccess(): MatricesAccess {
  return featureFlags.matricesIntegration ? realMatricesAccess : temporaryMockAccess;
}

export function isMatricesIntegrated(): boolean {
  return featureFlags.matricesIntegration;
}
