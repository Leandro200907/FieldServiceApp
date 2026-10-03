import type { EvidenciaVigente } from '../mi-legajo/contracts';
import type { LegajoCompuesto } from '../mi-legajo/contracts';
import { etiquetasEvidencia } from '../../ui/evidenciaPresentacion';

export type BucketDocumento = 'vencidos' | 'por_vencer' | 'en_revision' | 'vigentes';

export function todosLosDocumentos(data: LegajoCompuesto): EvidenciaVigente[] {
  return [...data.documentos, ...data.acreditaciones, ...data.inducciones];
}

function bucketDeItem(item: EvidenciaVigente): BucketDocumento {
  const labels = etiquetasEvidencia(item).map(l => l.toLowerCase());
  if (labels.some(l => l.includes('vencid'))) return 'vencidos';
  if (labels.some(l => l.includes('por vencer'))) return 'por_vencer';
  if (labels.some(l => l.includes('revisión') || l.includes('propuesta'))) return 'en_revision';
  return 'vigentes';
}

export function contarBuckets(items: EvidenciaVigente[]): Record<BucketDocumento, number> {
  const out: Record<BucketDocumento, number> = { vencidos: 0, por_vencer: 0, en_revision: 0, vigentes: 0 };
  for (const item of items) out[bucketDeItem(item)] += 1;
  return out;
}

export function enReglaCount(resumen: LegajoCompuesto['resumen']): { enRegla: number; total: number } {
  const total = resumen.total;
  const enRegla = Math.max(0, total - resumen.vencidos);
  return { enRegla, total };
}

export function proximoVencimientoIso(items: EvidenciaVigente[]): string | null {
  const futuros = items
    .filter(i => (i.dias_para_vencer ?? 0) >= 0 && !i.vencido)
    .sort((a, b) => (a.dias_para_vencer ?? 9999) - (b.dias_para_vencer ?? 9999));
  return futuros[0]?.vigente_hasta ?? null;
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
