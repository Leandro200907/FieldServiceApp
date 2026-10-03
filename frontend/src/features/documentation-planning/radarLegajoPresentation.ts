/** Presentación de requisitos evaluados en radar → Ver evidencia (ronda 1-b §7). */

import {
  etiquetaEstadoRequisitoDocumental,
  tonoEstadoRequisitoDocumental,
  type EtiquetaEstadoRequisitoDocumental,
} from '../../ui/estadoRequisitoPresentacion';

export type RadarRequisitoEvaluado = {
  nombre?: string | null;
  estado?: string | null;
  motivo?: string | null;
  vigente_hasta?: string | null;
  archivo_validacion?: string | null;
  requerido?: boolean | null;
};

export type EtiquetaEstadoRequisitoRadar = EtiquetaEstadoRequisitoDocumental;

export const etiquetaEstadoRequisitoRadar = etiquetaEstadoRequisitoDocumental;

export function tonoEstadoRequisitoRadar(
  etiqueta: EtiquetaEstadoRequisitoRadar,
): 'warning' | 'accent' {
  return tonoEstadoRequisitoDocumental(etiqueta);
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
