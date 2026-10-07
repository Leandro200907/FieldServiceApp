import type { EvidenciaVigente } from '../mi-legajo/contracts';
import type { LegajoCompuesto, ResumenLegajo } from '../mi-legajo/contracts';

export type BucketDocumento = 'vencidos' | 'por_vencer' | 'vigentes' | 'sin_documento';

export function todosLosDocumentos(data: LegajoCompuesto): EvidenciaVigente[] {
  return [...data.documentos, ...data.acreditaciones, ...data.inducciones];
}

/** Conteos de tarjetas E-101: solo `resumen.exigidos_*` del backend. */
type ResumenTarjetas = Pick<
  ResumenLegajo,
  'exigidos_vencidos' | 'exigidos_por_vencer' | 'exigidos_vigentes' | 'exigidos_sin_documento'
>;

export function conteosTarjetasExigidos(resumen: ResumenTarjetas): Record<BucketDocumento, number> {
  return {
    vencidos: resumen.exigidos_vencidos ?? 0,
    por_vencer: resumen.exigidos_por_vencer ?? 0,
    vigentes: resumen.exigidos_vigentes ?? 0,
    sin_documento: resumen.exigidos_sin_documento ?? 0,
  };
}

export function pendientesRevisionDesdeResumen(resumen: Pick<ResumenLegajo, 'pendientes_revision'>): number {
  return resumen.pendientes_revision ?? 0;
}

export function proximoVencimientoDesdeResumen(resumen: Pick<ResumenLegajo, 'proximo_vencimiento'>): string | null {
  return resumen.proximo_vencimiento ?? null;
}

export function ocsAfectadasUnicas(items: EvidenciaVigente[]): number {
  const ids = new Set<string>();
  for (const item of items) {
    for (const oc of item.ocs_afectadas ?? []) {
      const id = (oc as { oc_id?: string }).oc_id;
      if (id) ids.add(id);
    }
  }
  return ids.size;
}

export function resumenVencimientosTexto(vencidos: number, porVencer: number): string {
  const parts: string[] = [];
  if (vencidos > 0) parts.push(`${vencidos} vencido${vencidos === 1 ? '' : 's'}`);
  if (porVencer > 0) parts.push(`${porVencer} por vencer`);
  return parts.length ? parts.join(' · ') : 'Sin vencimientos pendientes';
}

/** E-96: texto del encabezado «Resumen» desde conteos exigidos del API (sin recalcular dominio). */
export function resumenExigidosTexto(resumen: {
  exigidos_sin_documento?: number;
  exigidos_vencidos?: number;
  exigidos_por_vencer?: number;
}): string {
  const parts: string[] = [];
  const sinDoc = resumen.exigidos_sin_documento ?? 0;
  const vencidos = resumen.exigidos_vencidos ?? 0;
  const porVencer = resumen.exigidos_por_vencer ?? 0;
  if (sinDoc > 0) parts.push(`${sinDoc} sin documento`);
  if (vencidos > 0) parts.push(`${vencidos} vencido${vencidos === 1 ? '' : 's'}`);
  if (porVencer > 0) parts.push(`${porVencer} por vencer`);
  return parts.length ? parts.join(' · ') : 'Sin pendientes';
}
