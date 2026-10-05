/** Texto de columna Observación en ficha de legajo (E-105). */

export type ObservacionFilaInput = {
  observacion_ficha?: string;
  observacion_operadora?: string;
  no_exigido_backlog?: boolean;
};

export function observacionFila(item: ObservacionFilaInput): string {
  if (item.observacion_operadora) {
    return item.observacion_operadora;
  }
  const parts: string[] = [];
  const ficha = item.observacion_ficha?.trim();
  if (ficha && ficha !== '—') parts.push(ficha);
  if (item.no_exigido_backlog) parts.push('No exigido por OC actuales');
  if (parts.length === 0) return '—';
  return parts.join(' · ');
}
