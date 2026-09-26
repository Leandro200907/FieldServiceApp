import { featureFlags } from '../../app/flags';
import type { DocumentationPlanningAccess } from './contracts';
import { realDocumentationPlanningAccess } from './realDocumentationPlanningAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real de todo el feature. Mientras
// El calendario y el radar se activan por separado. El servidor resuelve alcance y reglas;
// el frontend se limita a presentar el resultado contractual.
export function calendarAccess(): DocumentationPlanningAccess {
  return featureFlags.documentationCalendarIntegration ? realDocumentationPlanningAccess : temporaryMockAccess;
}

export function backlogAccess(): DocumentationPlanningAccess {
  return featureFlags.radarDocumentationIntegration ? realDocumentationPlanningAccess : temporaryMockAccess;
}

export function isCalendarIntegrated(): boolean {
  return featureFlags.documentationCalendarIntegration;
}

export function isBacklogIntegrated(): boolean {
  return featureFlags.radarDocumentationIntegration;
}


