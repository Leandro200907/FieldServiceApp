/** Etiqueta principal de un requisito evaluado (D19: vencido → sin respaldo → en revisión → vigente). */

export type EtiquetaEstadoRequisitoDocumental =
  | 'Vencido'
  | 'Vence durante la OC'
  | 'Sin respaldo'
  | 'En revisión'
  | 'Vigente';

export type RequisitoEvaluadoPresentacion = {
  estado?: string | null;
  archivo_validacion?: string | null;
};

/** Misma precedencia que D19 / motor documental. */
export function etiquetaEstadoRequisitoDocumental(
  req: RequisitoEvaluadoPresentacion,
): EtiquetaEstadoRequisitoDocumental {
  const estado = req.estado ?? '';
  if (estado === 'vencido_antes_inicio' || estado === 'faltante') return 'Vencido';
  if (estado === 'vence_durante_periodo') return 'Vence durante la OC';
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

export function tonoEstadoRequisitoDocumental(
  etiqueta: EtiquetaEstadoRequisitoDocumental,
): 'warning' | 'accent' {
  return etiqueta === 'Vigente' ? 'accent' : 'warning';
}
