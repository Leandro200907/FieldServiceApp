// Release gates, not authorization. No capability is inferred from version strings.
export const featureFlags = Object.freeze({
  drive: false, notifications: false, documentPackageQr: false,
  documentScore: false, legajoExport: false, alertConfiguration: false,
  alertLifecycle: false, globalTemplates: false, module2Integration: false,
  documentBatchImport: false, typedBusinessViews: false, signedEvidence: false,
  technicianCompositeView: true,
  documentationCalendarIntegration: true, backlogDocumentationIntegration: true,
  expirationsBoardIntegration: true, legajoLookupIntegration: true,
});
