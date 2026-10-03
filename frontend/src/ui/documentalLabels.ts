import type { RadarState } from '../features/documentation-planning/contracts';

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
