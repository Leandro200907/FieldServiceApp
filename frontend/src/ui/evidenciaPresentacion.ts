import type { EvidenciaVigente } from '../features/mi-legajo/contracts';
import { deriveVisualState, type VisualCalendarState } from '../features/documentation-planning/contracts';

export const estadoPresentacionLabels: Record<string, string> = {
  verificada: 'Verificada',
  declarada: 'Declarada',
  por_vencer: 'Por vencer',
  vencida: 'Vencida',
  archivo_en_revision: 'Archivo en revisión',
  evidencia_invalida: 'Evidencia inválida',
  sin_archivo_respaldo: 'Sin archivo de respaldo',
  propuesta_en_revision: 'Propuesta en revisión',
};

const visualStateLabels: Record<VisualCalendarState, string> = {
  verificada: 'Verificada',
  vencida: 'Vencida',
  declarada: 'Declarada',
};

const ESTADOS_VIGENCIA = new Set(['verificada', 'declarada', 'por_vencer', 'vencida', 'propuesta_en_revision']);
const ESTADOS_RESPALDO = new Set(['archivo_en_revision', 'evidencia_invalida', 'sin_archivo_respaldo']);

function etiquetaDeCodigo(codigo: string): string {
  return estadoPresentacionLabels[codigo] ?? codigo;
}

export function etiquetaVigencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido'>,
): string {
  const presentacion = item.estado_presentacion;
  if (presentacion && ESTADOS_VIGENCIA.has(presentacion)) {
    return etiquetaDeCodigo(presentacion);
  }
  if (presentacion && ESTADOS_RESPALDO.has(presentacion)) {
    const dias = item.dias_para_vencer ?? 0;
    return visualStateLabels[deriveVisualState({ estado_confirmacion: item.estado_confirmacion, dias_para_vencer: dias })];
  }
  const dias = item.dias_para_vencer ?? 0;
  return visualStateLabels[deriveVisualState({ estado_confirmacion: item.estado_confirmacion, dias_para_vencer: dias })];
}

export function etiquetasRespaldo(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estados_adicionales'>,
): string[] {
  const codigos: string[] = [];
  if (item.estado_presentacion && ESTADOS_RESPALDO.has(item.estado_presentacion)) {
    codigos.push(item.estado_presentacion);
  }
  for (const extra of item.estados_adicionales ?? []) {
    if (ESTADOS_RESPALDO.has(extra) && !codigos.includes(extra)) {
      codigos.push(extra);
    }
  }
  return codigos.map(etiquetaDeCodigo);
}

/** Etiquetas de vigencia y de respaldo (dos dimensiones independientes). */
export function etiquetasEvidencia(
  item: Pick<
    EvidenciaVigente,
    'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido' | 'estados_adicionales'
  >,
): string[] {
  if (item.estado_presentacion === 'propuesta_en_revision') {
    return [etiquetaDeCodigo('propuesta_en_revision')];
  }
  const vigencia = etiquetaVigencia(item);
  const respaldo = etiquetasRespaldo(item);
  const out = [vigencia, ...respaldo.filter(r => r !== vigencia)];
  return out.length ? out : [vigencia];
}

/** @deprecated Preferir etiquetasEvidencia para mostrar vigencia y respaldo por separado. */
export function etiquetaEvidencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido' | 'estados_adicionales'>,
): string {
  return etiquetasEvidencia(item)[0] ?? '—';
}

export function tonoEvidencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido' | 'estados_adicionales'>,
): 'warning' | 'accent' {
  const codigos = [
    item.estado_presentacion,
    ...(item.estados_adicionales ?? []),
  ].filter(Boolean) as string[];
  if (codigos.some(c => c === 'vencida' || c === 'evidencia_invalida') || item.vencido) return 'warning';
  if (codigos.some(c => c === 'por_vencer' || c === 'propuesta_en_revision' || c === 'archivo_en_revision' || c === 'sin_archivo_respaldo')) {
    return 'warning';
  }
  return 'accent';
}

export function textoPropuestaEnRevision(
  propuesta: NonNullable<EvidenciaVigente['propuesta_en_revision']>,
): string {
  const hasta = propuesta.vigente_hasta;
  if (!hasta) return 'Propuesta en revisión: nueva versión pendiente de confirmación';
  const [y, m, d] = hasta.split('-');
  const fecha = d && m && y ? `${d}/${m}/${y}` : hasta;
  return `Propuesta en revisión: nueva versión hasta ${fecha}`;
}
