import { formatFecha } from '../features/documentation-planning/dates';

export type OcAfectadaRef = {
  clave_origen: string;
  oc_id?: string;
  vigencia_desde: string;
  vigencia_hasta: string;
};

export function ocEnCurso(oc: OcAfectadaRef, hoyIso: string): boolean {
  return oc.vigencia_desde <= hoyIso && hoyIso <= oc.vigencia_hasta;
}

export function ordenarOcsAfectadas(ocs: OcAfectadaRef[], hoyIso: string): OcAfectadaRef[] {
  return [...ocs].sort((a, b) => {
    const aCurso = ocEnCurso(a, hoyIso) ? 0 : 1;
    const bCurso = ocEnCurso(b, hoyIso) ? 0 : 1;
    if (aCurso !== bCurso) return aCurso - bCurso;
    return a.vigencia_desde.localeCompare(b.vigencia_desde);
  });
}

function etiquetaOc(
  oc: OcAfectadaRef,
  hoyIso: string,
  format: (iso: string) => string,
): string {
  if (ocEnCurso(oc, hoyIso)) return `${oc.clave_origen} (en curso)`;
  return `${oc.clave_origen} (desde ${format(oc.vigencia_desde)})`;
}

export function textoListaCompletaOcsAfectadas(
  ocs: OcAfectadaRef[],
  hoyIso: string,
  timeZone: string,
): string {
  const format = (iso: string) => formatFecha(iso, timeZone);
  return ordenarOcsAfectadas(ocs, hoyIso).map(oc => etiquetaOc(oc, hoyIso, format)).join(', ');
}

/** Resumen visible y título con la lista completa (hover / foco). */
export function resumenOcsAfectadas(
  ocs: OcAfectadaRef[],
  hoyIso: string,
  timeZone: string,
): { resumen: string; tituloCompleto: string } | null {
  if (!ocs.length) return null;
  const format = (iso: string) => formatFecha(iso, timeZone);
  const ordenadas = ordenarOcsAfectadas(ocs, hoyIso);
  const etiquetas = ordenadas.map(oc => etiquetaOc(oc, hoyIso, format));
  const n = ordenadas.length;
  const resumen = `Afecta ${n} OC`;
  return { resumen, tituloCompleto: etiquetas.join(', ') };
}
