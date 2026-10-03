/** Presentación de requisitos evaluados en radar → Ver evidencia (ronda 1-b §7). */

export type RadarRequisitoEvaluado = {
  nombre?: string | null;
  estado?: string | null;
  motivo?: string | null;
  vigente_hasta?: string | null;
  archivo_validacion?: string | null;
  requerido?: boolean | null;
};

const ESTADOS_VENCIDO = new Set([
  'vencido_antes_inicio',
  'vence_durante_periodo',
  'faltante',
]);

export type EtiquetaEstadoRequisitoRadar = 'Vencido' | 'Sin respaldo' | 'En revisión' | 'Vigente';

/** Misma precedencia que D19 / motor documental: vencido → sin respaldo → en revisión → vigente. */
export function etiquetaEstadoRequisitoRadar(
  req: Pick<RadarRequisitoEvaluado, 'estado' | 'archivo_validacion'>,
): EtiquetaEstadoRequisitoRadar {
  const estado = req.estado ?? '';
  if (ESTADOS_VENCIDO.has(estado)) return 'Vencido';
  if (estado === 'vigente_todo_el_periodo') return 'Vigente';
  if (estado === 'evidencia_invalida') return 'Sin respaldo';
  if (estado === 'pendiente_revision') {
    const arch = req.archivo_validacion;
    if (arch === 'sin_archivo' || arch === 'invalido') return 'Sin respaldo';
    return 'En revisión';
  }
  if (estado === 'no_evaluable') return 'En revisión';
  return 'En revisión';
}

export function tonoEstadoRequisitoRadar(
  etiqueta: EtiquetaEstadoRequisitoRadar,
): 'warning' | 'accent' {
  return etiqueta === 'Vigente' ? 'accent' : 'warning';
}

export function requisitosRadarVisibles(requisitos: RadarRequisitoEvaluado[]): RadarRequisitoEvaluado[] {
  return requisitos.filter(r => r.requerido !== false);
}

export function motivoFalloRequisitoRadar(
  req: RadarRequisitoEvaluado,
): string | null {
  if (etiquetaEstadoRequisitoRadar(req) === 'Vigente') return null;
  const motivo = req.motivo?.trim();
  return motivo || null;
}

export function tituloLegajoRadar(legajo: {
  tipo_sujeto?: string | null;
  nombre_apellido?: string | null;
  identificador_natural?: string | null;
}): string {
  if (legajo.tipo_sujeto === 'persona' && legajo.nombre_apellido) {
    const id = legajo.identificador_natural?.trim();
    return id ? `${legajo.nombre_apellido} · DNI ${id}` : legajo.nombre_apellido;
  }
  return legajo.identificador_natural?.trim() || 'Legajo';
}

export function textoVencimientoRequisitoRadar(
  vigenteHasta: string | null | undefined,
  formatFecha: (iso: string) => string,
): string {
  if (!vigenteHasta) return 'Sin vencimiento';
  return `Vence ${formatFecha(vigenteHasta)}`;
}
