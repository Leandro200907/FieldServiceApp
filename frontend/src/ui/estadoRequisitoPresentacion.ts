/** Etiqueta principal de un requisito evaluado (radar): código del motor → texto visible. */

export type EtiquetaEstadoRequisitoDocumental =
  | 'Vencido'
  | 'Vence durante la OC'
  | 'Sin respaldo'
  | 'En revisión'
  | 'Vigente';

export type RequisitoEvaluadoPresentacion = {
  estado?: string | null;
};

const etiquetasPorEstadoMotor: Record<string, EtiquetaEstadoRequisitoDocumental> = {
  vencido_antes_inicio: 'Vencido',
  faltante: 'Vencido',
  vence_durante_periodo: 'Vence durante la OC',
  vigente_todo_el_periodo: 'Vigente',
  evidencia_invalida: 'Sin respaldo',
  pendiente_revision: 'En revisión',
  no_evaluable: 'En revisión',
};

/** Mapa código → texto; sin reglas de archivo ni calendario en el front. */
export function etiquetaEstadoRequisitoDocumental(
  req: RequisitoEvaluadoPresentacion,
): EtiquetaEstadoRequisitoDocumental {
  const estado = req.estado ?? '';
  return etiquetasPorEstadoMotor[estado] ?? 'En revisión';
}

export function tonoEstadoRequisitoDocumental(
  etiqueta: EtiquetaEstadoRequisitoDocumental,
): 'warning' | 'accent' {
  return etiqueta === 'Vigente' ? 'accent' : 'warning';
}
