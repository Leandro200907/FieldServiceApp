import type { EvidenciaVigente } from '../features/mi-legajo/contracts';
import { deriveVisualState, type VisualCalendarState } from '../features/documentation-planning/contracts';

export const estadoPresentacionLabels: Record<string, string> = {
  verificada: 'Verificada',
  declarada: 'Declarada',
  por_vencer: 'Por vencer',
  vencida: 'Vencida',
  archivo_en_revision: 'Archivo en revisión',
  evidencia_invalida: 'Evidencia inválida',
  propuesta_en_revision: 'Propuesta en revisión',
};

const visualStateLabels: Record<VisualCalendarState, string> = {
  verificada: 'Verificada',
  vencida: 'Vencida',
  declarada: 'Declarada',
};

export function etiquetaEvidencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer'>,
): string {
  const presentacion = item.estado_presentacion;
  if (presentacion) {
    return estadoPresentacionLabels[presentacion] ?? presentacion;
  }
  const dias = item.dias_para_vencer ?? 0;
  return visualStateLabels[deriveVisualState({ estado_confirmacion: item.estado_confirmacion, dias_para_vencer: dias })];
}

export function tonoEvidencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido'>,
): 'warning' | 'accent' {
  const est = item.estado_presentacion;
  if (est === 'vencida' || est === 'evidencia_invalida' || item.vencido) return 'warning';
  if (est === 'por_vencer' || est === 'propuesta_en_revision' || est === 'archivo_en_revision') return 'warning';
  return 'accent';
}
