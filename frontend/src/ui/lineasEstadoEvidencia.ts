import type { EvidenciaVigente } from '../features/mi-legajo/contracts';
import { etiquetasEvidencia, textoPropuestaEnRevision } from './evidenciaPresentacion';

/** E-93: separar versión vigente y renovación en revisión. */
export function lineasVersionYRenovacion(item: EvidenciaVigente): { actual: string | null; renovacion: string | null } {
  if (!item.propuesta_en_revision) {
    return { actual: null, renovacion: null };
  }
  const labels = etiquetasEvidencia({ ...item, propuesta_en_revision: undefined });
  const actual = `Versión actual: ${labels.join(', ').toLowerCase()}`;
  const renovacion = textoPropuestaEnRevision(item.propuesta_en_revision).replace('Propuesta en revisión: ', 'Renovación en revisión, ');
  return { actual, renovacion };
}
