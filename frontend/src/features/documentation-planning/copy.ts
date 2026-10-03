import { formatFecha } from './dates';

export function textoEfectoAccion(efecto: string): string {
  return efecto.replace(/cobertura documental/gi, 'disponibilidad documental');
}

export function textoAccionSugerida(accion: string, fecha: string | null | undefined, timeZone: string): string {
  if (!fecha) return accion;
  return `${accion} ${formatFecha(fecha, timeZone)}`.trim();
}

/** E-32: mensaje cuando el documento ya venció en una OC en curso. */
/** Acción corta para la columna «Qué hacer» (E-65). */
export function accionCorta(accion: string): string {
  const a = accion.toLowerCase();
  if (a.includes('renovar')) return 'Renovar';
  if (a.includes('incorporar') || a.includes('cargar')) return 'Incorporar archivo';
  if (a.includes('reemplazar') || a.includes('validar') || a.includes('regulariz')) return 'Regularizar';
  if (a.includes('revisar') || a.includes('confirmar')) return 'Revisar';
  if (a.includes('corregir') || a.includes('completar')) return 'Completar';
  return accion.split(/[.:]/)[0]?.trim() || accion;
}

export function textoQueHacerAccion(
  accion: string,
  fechaLimite: string,
  hoyIso: string,
  timeZone: string,
): string {
  const corta = accionCorta(accion);
  if (fechaLimite <= hoyIso) {
    return `Vencido: bloquea desde ${formatFecha(fechaLimite, timeZone)}. ${corta === 'Renovar' ? 'Renovar ya.' : corta + '.'}`;
  }
  return corta;
}
