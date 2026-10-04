import { formatFecha } from '../../ui/fechas';

const MAX_ANIOS = 10;

export function validarFechaRenovacion(
  vigenteHastaNueva: string,
  vigenteHastaActual: string,
  hoyIso: string,
  timeZone: string,
): string | null {
  if (!vigenteHastaNueva) return 'Elegí la nueva fecha de vencimiento.';
  const nueva = new Date(`${vigenteHastaNueva}T12:00:00`);
  const hoy = new Date(`${hoyIso}T12:00:00`);
  const actual = new Date(`${vigenteHastaActual}T12:00:00`);
  if (Number.isNaN(nueva.getTime())) return 'La fecha no es válida.';
  if (nueva <= hoy) return 'La nueva fecha de vencimiento tiene que ser posterior a hoy.';
  if (nueva <= actual) {
    const ref = formatFecha(vigenteHastaActual, timeZone);
    return `La nueva fecha de vencimiento tiene que ser posterior al ${ref} (vencimiento actual).`;
  }
  const tope = new Date(hoy);
  tope.setFullYear(tope.getFullYear() + MAX_ANIOS);
  if (nueva > tope) {
    return `La nueva fecha de vencimiento no puede superar ${MAX_ANIOS} años desde hoy.`;
  }
  return null;
}

export function mensajeErrorApiRenovacion(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes('vigencia_no_futura') || lower.includes('posterior a hoy')) {
    return 'La nueva fecha de vencimiento tiene que ser posterior a hoy.';
  }
  if (lower.includes('vigencia_no_posterior_a_vigente') || lower.includes('posterior a la vigencia actual')) {
    return 'La nueva fecha de vencimiento tiene que ser posterior al vencimiento actual del documento.';
  }
  if (lower.includes('vigencia_propuesta_excede_plazo') || lower.includes('10 años')) {
    return 'La nueva fecha de vencimiento no puede superar 10 años desde hoy.';
  }
  if (lower.includes('vigente_desde no puede ser posterior')) {
    return 'Revisá la fecha de vencimiento: tiene que ser posterior a hoy y al vencimiento actual.';
  }
  return message;
}
