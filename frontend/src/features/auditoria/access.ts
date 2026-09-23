import { featureFlags } from '../../app/flags';
import type { AuditoriaAccess } from './contracts';
import { realAuditoriaAccess } from './realAuditoriaAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real (mismo patrón que el resto de features).
export function auditoriaAccess(): AuditoriaAccess {
  return featureFlags.auditLogIntegration ? realAuditoriaAccess : temporaryMockAccess;
}

export function isAuditoriaIntegrated(): boolean {
  return featureFlags.auditLogIntegration;
}
