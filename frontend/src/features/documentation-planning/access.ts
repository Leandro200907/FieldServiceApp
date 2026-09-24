import { featureFlags } from '../../app/flags';
import type { DocumentationPlanningAccess } from './contracts';
import { realDocumentationPlanningAccess } from './realDocumentationPlanningAccess';
import { temporaryMockAccess } from './temporaryMockAccess';

// Único punto de decisión mock-vs-real de todo el feature. Mientras
// `documentationCalendarIntegration`/`backlogDocumentationIntegration` sigan en `false`
// (ver app/flags.ts), las pantallas siguen mostrando el mock rotulado — cambiar el flag es
// la única acción necesaria para pasar a datos reales, no hace falta tocar ningún
// componente. Los dos endpoints son independientes: el calendario puede integrarse antes
// (o después) que el backlog/detalle.
export function calendarAccess(): DocumentationPlanningAccess {
  return featureFlags.documentationCalendarIntegration ? realDocumentationPlanningAccess : temporaryMockAccess;
}

export function backlogAccess(): DocumentationPlanningAccess {
  return featureFlags.backlogDocumentationIntegration ? realDocumentationPlanningAccess : temporaryMockAccess;
}

export function isCalendarIntegrated(): boolean {
  return featureFlags.documentationCalendarIntegration;
}

export function isBacklogIntegrated(): boolean {
  return featureFlags.backlogDocumentationIntegration;
}
