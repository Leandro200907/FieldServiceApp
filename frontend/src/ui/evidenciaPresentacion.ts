import type { EvidenciaVigente } from '../features/mi-legajo/contracts';

export const estadoPresentacionLabels: Record<string, string> = {
  verificada: 'Verificada',
  declarada: 'Declarada',
  vigente: 'Vigente',
  por_vencer: 'Por vencer',
  vencida: 'Vencida',
  archivo_en_revision: 'Archivo en revisión',
  evidencia_invalida: 'Evidencia inválida',
  sin_archivo_respaldo: 'Sin archivo de respaldo',
  propuesta_en_revision: 'Propuesta en revisión',
};

const ESTADOS_RESPALDO = new Set(['archivo_en_revision', 'evidencia_invalida', 'sin_archivo_respaldo']);
const ESTADOS_CONFIRMACION = new Set(['declarada', 'verificada']);

function etiquetaDeCodigo(codigo: string): string {
  return estadoPresentacionLabels[codigo] ?? codigo;
}

/** Código de vigencia por fechas (independiente de confirmación y archivo). */
function codigoVigencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'dias_para_vencer' | 'vencido'>,
): 'vigente' | 'por_vencer' | 'vencida' {
  const presentacion = item.estado_presentacion;
  if (presentacion === 'por_vencer') return 'por_vencer';
  if (presentacion === 'vencida' || item.vencido || (item.dias_para_vencer ?? 0) < 0) return 'vencida';
  if (presentacion === 'verificada' || presentacion === 'vigente') return 'vigente';
  if (presentacion === 'declarada') {
    return item.vencido || (item.dias_para_vencer ?? 0) < 0 ? 'vencida' : 'vigente';
  }
  if (presentacion && ESTADOS_RESPALDO.has(presentacion)) {
    return item.vencido || (item.dias_para_vencer ?? 0) < 0 ? 'vencida' : 'vigente';
  }
  return 'vigente';
}

export function etiquetaVigencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido'>,
): string {
  const codigo = codigoVigencia(item);
  if (codigo === 'vigente') return 'Vigente';
  return etiquetaDeCodigo(codigo);
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

function etiquetasConfirmacion(
  item: Pick<EvidenciaVigente, 'estado_confirmacion' | 'estados_adicionales'>,
): string[] {
  const codigos: string[] = [];
  for (const extra of item.estados_adicionales ?? []) {
    if (ESTADOS_CONFIRMACION.has(extra) && extra === 'declarada' && !codigos.includes(extra)) {
      codigos.push(extra);
    }
  }
  if (item.estado_confirmacion === 'declarado' && !codigos.includes('declarada')) {
    codigos.push('declarada');
  }
  return codigos.map(etiquetaDeCodigo);
}

/** Etiquetas de vigencia, confirmación y respaldo (dimensiones independientes). */
export function etiquetasEvidencia(
  item: Pick<
    EvidenciaVigente,
    'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido' | 'estados_adicionales'
  > & { propuesta_en_revision?: EvidenciaVigente['propuesta_en_revision'] },
): string[] {
  if (item.estado_presentacion === 'propuesta_en_revision' && !item.propuesta_en_revision) {
    return [etiquetaDeCodigo('propuesta_en_revision')];
  }
  const vigencia = etiquetaVigencia(item);
  const confirmacion = etiquetasConfirmacion(item);
  const respaldo = etiquetasRespaldo(item);
  const out = [vigencia, ...confirmacion, ...respaldo.filter(r => r !== vigencia && !confirmacion.includes(r))];
  return out.length ? out : [vigencia];
}

/** @deprecated Preferir etiquetasEvidencia para mostrar vigencia y respaldo por separado. */
export function etiquetaEvidencia(
  item: Pick<EvidenciaVigente, 'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido' | 'estados_adicionales'>,
): string {
  return etiquetasEvidencia(item)[0] ?? '—';
}

export function tonoEvidencia(
  item: Pick<
    EvidenciaVigente,
    'estado_presentacion' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido' | 'estados_adicionales' | 'propuesta_en_revision'
  >,
): 'warning' | 'accent' {
  const codigoVig = codigoVigencia(item);
  const codigos = [
    item.estado_presentacion,
    ...(item.estados_adicionales ?? []),
  ].filter(Boolean) as string[];
  if (codigoVig === 'vencida' || codigos.some(c => c === 'evidencia_invalida') || item.vencido) return 'warning';
  if (
    codigoVig === 'por_vencer'
    || codigos.some(c => c === 'propuesta_en_revision' || c === 'archivo_en_revision' || c === 'sin_archivo_respaldo')
    || item.propuesta_en_revision
  ) {
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
