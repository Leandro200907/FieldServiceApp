/** Presentación de requisitos evaluados en radar → Ver evidencia (ronda 1-b §7). */

import {
  etiquetaEstadoRequisitoDocumental,
  tonoEstadoRequisitoDocumental,
  type EtiquetaEstadoRequisitoDocumental,
} from '../../ui/estadoRequisitoPresentacion';
import { diasInclusivos } from './dates';

export type RadarRequisitoEvaluado = {
  nombre?: string | null;
  estado?: string | null;
  motivo?: string | null;
  vigente_hasta?: string | null;
  primer_quiebre?: string | null;
  periodo_hasta?: string | null;
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

/** Período sin cobertura dentro de la OC (solo `vence_durante_periodo`). */
export function textoSinCoberturaRequisitoRadar(
  req: RadarRequisitoEvaluado,
  periodoHastaOc: string | null | undefined,
  formatFecha: (iso: string) => string,
): string | null {
  if (req.estado !== 'vence_durante_periodo') return null;
  const desde = req.primer_quiebre?.trim();
  const hasta = (periodoHastaOc?.trim() || req.periodo_hasta?.trim()) ?? '';
  if (!desde || !hasta || hasta < desde) return null;
  const dias = diasInclusivos(desde, hasta);
  const diasLabel = dias === 1 ? '1 día' : `${dias} días`;
  return `Sin cobertura del ${formatFecha(desde)} al ${formatFecha(hasta)} (${diasLabel})`;
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
