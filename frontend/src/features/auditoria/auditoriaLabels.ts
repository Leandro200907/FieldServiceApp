/** Acciones de auditoría en castellano (E-46 / E-47). */
export const tipoEventoAuditoriaLabels: Record<string, string> = {
  DocumentoConfirmado: 'Documento confirmado',
  DocumentoRechazado: 'Documento rechazado',
  DocumentoCargado: 'Documento cargado',
  DocumentoVencido: 'Documento vencido',
  SupervisorAsignado: 'Supervisor asignado',
  ExcepcionRegularizada: 'Excepción regularizada',
};

export function labelTipoEventoAuditoria(tipo: string): string {
  return tipoEventoAuditoriaLabels[tipo] ?? tipo.replace(/([a-z])([A-Z])/g, '$1 $2');
}

export const tiposEventoAuditoriaOpciones = Object.entries(tipoEventoAuditoriaLabels).map(([value, label]) => ({ value, label }));
