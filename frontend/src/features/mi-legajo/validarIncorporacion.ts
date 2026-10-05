const MAX_ANIOS = 10;

export function validarFechaIncorporacion(vigenteHastaNueva: string, hoyIso: string, _timeZone?: string): string | null {
  if (!vigenteHastaNueva) return 'Elegí la fecha de vencimiento.';
  const nueva = new Date(`${vigenteHastaNueva}T12:00:00`);
  const hoy = new Date(`${hoyIso}T12:00:00`);
  if (Number.isNaN(nueva.getTime())) return 'La fecha no es válida.';
  if (nueva <= hoy) return 'La fecha de vencimiento tiene que ser posterior a hoy.';
  const tope = new Date(hoy);
  tope.setFullYear(tope.getFullYear() + MAX_ANIOS);
  if (nueva > tope) {
    return `La fecha de vencimiento no puede superar ${MAX_ANIOS} años desde hoy.`;
  }
  return null;
}

export function mensajeErrorApiIncorporacion(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes('vigencia_no_futura') || lower.includes('posterior a hoy')) {
    return 'La fecha de vencimiento tiene que ser posterior a hoy.';
  }
  if (lower.includes('vigencia_propuesta_excede_plazo') || lower.includes('10 años')) {
    return 'La fecha de vencimiento no puede superar 10 años desde hoy.';
  }
  return message;
}
