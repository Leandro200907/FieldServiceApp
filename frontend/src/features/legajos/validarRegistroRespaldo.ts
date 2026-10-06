const MAX_ANIOS = 10;
export const MAX_BYTES_CERTIFICADO = 25 * 1024 * 1024;
export const TIPOS_CERTIFICADO_PERMITIDOS = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/webp',
]);

export function validarFechaRealizacion(vigenteDesde: string, hoyIso: string): string | null {
  if (!vigenteDesde) return 'Elegí la fecha de realización.';
  const desde = new Date(`${vigenteDesde}T12:00:00`);
  const hoy = new Date(`${hoyIso}T12:00:00`);
  if (Number.isNaN(desde.getTime())) return 'La fecha no es válida.';
  if (desde > hoy) return 'La fecha de realización no puede ser futura.';
  return null;
}

/** Mismas reglas que incorporación/renovación para el vencimiento de un registro nuevo. */
export function validarFechaVencimientoRespaldo(vigenteHasta: string, hoyIso: string): string | null {
  if (!vigenteHasta) return 'Elegí la fecha de vencimiento.';
  const nueva = new Date(`${vigenteHasta}T12:00:00`);
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

export function validarArchivoCertificado(archivo: File): string | null {
  const tipo = archivo.type || '';
  if (!TIPOS_CERTIFICADO_PERMITIDOS.has(tipo)) {
    return 'El archivo tiene que ser PDF, JPEG, PNG o WebP.';
  }
  if (archivo.size > MAX_BYTES_CERTIFICADO) {
    return 'El archivo no puede superar 25 MiB.';
  }
  return null;
}

export function mensajeErrorApiRegistroRespaldo(message: string, code?: string, status?: number): string {
  const lower = message.toLowerCase();
  if (code === 'respaldo_tipo_no_admitido') {
    return 'Solo se admite un certificado de respaldo propio; no podés usar un documento del legajo.';
  }
  if (code === 'prohibido' || status === 403) {
    return 'No tenés permiso para registrar este respaldo. Pedí ayuda a Responsable de legajos.';
  }
  if (code === 'vigencia_desde_futura' || lower.includes('vigente_desde') && lower.includes('futur')) {
    return 'La fecha de realización no puede ser futura.';
  }
  if (lower.includes('vigencia_no_futura') || lower.includes('posterior a hoy')) {
    return 'La fecha de vencimiento tiene que ser posterior a hoy.';
  }
  if (lower.includes('vigencia_propuesta_excede_plazo') || lower.includes('10 años')) {
    return 'La fecha de vencimiento no puede superar 10 años desde hoy.';
  }
  if (lower.includes('content_type') || lower.includes('tipo de archivo') || lower.includes('no permitido')) {
    return 'El archivo tiene que ser PDF, JPEG, PNG o WebP.';
  }
  if (lower.includes('max_bytes') || lower.includes('demasiado grande') || lower.includes('25')) {
    return 'El archivo no puede superar 25 MiB.';
  }
  if (lower.includes('invalido') || lower.includes('inválido')) {
    return 'El archivo no pasó la validación técnica. Revisá el certificado y volvé a intentar.';
  }
  return message;
}
