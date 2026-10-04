import type { RadarState } from '../features/documentation-planning/contracts';
import type { StatusVariant } from './StatusDot';

/** Etiquetas legibles para códigos de estado documental de OC (sin exponer el enum crudo). */
export const estadoDocumentalOcLabels: Record<RadarState, string> = {
  sin_alertas_documentales: 'En regla',
  con_alertas_documentales: 'Con alertas',
  informacion_incompleta: 'Información incompleta',
  sin_matriz: 'Sin matriz aplicable',
  fuera_de_alcance: 'Fuera de tu alcance',
};

export function labelEstadoDocumentalOc(codigo: string): string {
  return estadoDocumentalOcLabels[codigo as RadarState] ?? codigo.replaceAll('_', ' ');
}

export function labelEstadoDocumentalOcConMatriz(
  codigo: string,
  ctx?: { operadora_nombre?: string | null; locacion_nombre?: string | null },
): string {
  if (codigo === 'sin_matriz') {
    const parte = [ctx?.operadora_nombre, ctx?.locacion_nombre].filter(Boolean).join(' · ');
    if (parte) return `Sin matriz aplicable. Falta cargar la matriz de ${parte}`;
  }
  return labelEstadoDocumentalOc(codigo);
}

/** Colores de estado documental de OC unificados en toda la app (E-18 / E-19). */
export function variantEstadoDocumentalOc(codigo: string): StatusVariant {
  if (codigo === 'sin_alertas_documentales') return 'vigente';
  if (codigo === 'con_alertas_documentales') return 'por_vencer';
  if (codigo === 'informacion_incompleta') return 'revision';
  if (codigo === 'sin_matriz') return 'neutral';
  return 'neutral';
}
