import { formatFecha } from './dates';

export function textoEfectoAccion(efecto: string): string {
  return efecto.replace(/cobertura documental/gi, 'disponibilidad documental');
}

export function textoAccionSugerida(accion: string, fecha: string | null | undefined, timeZone: string): string {
  if (!fecha) return accion;
  return `${accion} ${formatFecha(fecha, timeZone)}`.trim();
}

/** E-32: mensaje cuando el documento ya venció en una OC en curso. */
export function textoQueHacerAccion(
  accion: string,
  fechaLimite: string,
  hoyIso: string,
  timeZone: string,
): string {
  if (fechaLimite < hoyIso) {
    return `Vencido: bloquea desde ${formatFecha(fechaLimite, timeZone)}. Renovar ya.`;
  }
  return textoAccionSugerida(accion, fechaLimite, timeZone);
}
