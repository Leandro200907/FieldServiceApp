/** Acciones de auditoría en castellano (E-46). */
export const tipoEventoAuditoriaLabels: Record<string, string> = {
  DocumentoConfirmado: 'Documento confirmado',
  DocumentoRechazado: 'Documento rechazado',
  DocumentoCargado: 'Documento cargado',
  DocumentoVencido: 'Documento vencido',
  SupervisorAsignado: 'Supervisor asignado',
  ExcepcionRegularizada: 'Excepción regularizada',
  LocacionOcCreada: 'Locación creada',
  OperadoraOcCreada: 'Operadora creada',
  TipoServicioOcCreado: 'Tipo de servicio creado',
  NotificacionEmitida: 'Notificación emitida',
  AlertaDeVencimientoReconocida: 'Alerta de vencimiento reconocida',
  AlertaDeVencimientoAbierta: 'Alerta de vencimiento abierta',
  AlertaPausada: 'Alerta pausada',
  AlertaResuelta: 'Alerta resuelta',
  AlertaEscalada: 'Alerta escalada',
  LegajoCreado: 'Legajo creado',
  LegajoDadoDeBaja: 'Legajo dado de baja',
  PlanillaOperadorasImportada: 'Planilla de operadoras importada',
  EvidenciaAdjuntada: 'Evidencia adjuntada',
  CumplimientoEmpresaAfectado: 'Cumplimiento de empresa afectado',
  OcSinMatriz: 'OC sin matriz',
};

export function labelTipoEventoAuditoria(tipo: string): string {
  return tipoEventoAuditoriaLabels[tipo] ?? tipo.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^\w/, c => c.toUpperCase());
}

export const tiposEventoAuditoriaOpciones = Object.entries(tipoEventoAuditoriaLabels).map(([value, label]) => ({ value, label }));
