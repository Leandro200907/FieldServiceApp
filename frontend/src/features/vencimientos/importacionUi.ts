import type { SafeApiError } from '../../api';

type FilaImportError = { fila?: number | null; mensaje: string };

export function etiquetaFilaImportacion(fila: number | null | undefined): string {
  return fila == null ? 'Fila sin número' : `Fila ${fila}`;
}

export function erroresDesdeImportacion(error: SafeApiError | null): FilaImportError[] {
  if (!error?.details || typeof error.details !== 'object' || Array.isArray(error.details)) return [];
  const errores = (error.details as { errores?: unknown }).errores;
  if (!Array.isArray(errores)) return [];
  return errores.flatMap(item => {
    if (!item || typeof item !== 'object') return [];
    const fila = 'fila' in item ? (item as { fila?: number | null }).fila : undefined;
    const mensaje = typeof (item as { mensaje?: unknown }).mensaje === 'string' ? (item as { mensaje: string }).mensaje : null;
    return mensaje ? [{ fila, mensaje }] : [];
  });
}

export function buildOperadoraFilterOpts(
  catalogo: readonly { operadora_id: string; nombre: string }[],
  seleccionadas: readonly string[],
  respaldo: ReadonlyMap<string, string>,
): { operadora_id: string; nombre: string }[] {
  const map = new Map(catalogo.map(o => [o.operadora_id, o.nombre]));
  seleccionadas.forEach(id => {
    if (!map.has(id) && respaldo.has(id)) map.set(id, respaldo.get(id)!);
  });
  return [...map.entries()]
    .map(([operadora_id, nombre]) => ({ operadora_id, nombre }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
}

export function toggleSearchListParam(params: URLSearchParams, key: string, value: string): URLSearchParams {
  const next = new URLSearchParams(params);
  const cur = next.getAll(key);
  next.delete(key);
  if (cur.includes(value)) cur.filter(x => x !== value).forEach(x => next.append(key, x));
  else [...cur, value].forEach(x => next.append(key, x));
  return next;
}

export const ESTADO_HISTORIAL_LABELS: Record<string, string> = {
  exportado: 'Exportado',
  enviado: 'Enviado',
  aceptado: 'Aceptado',
  rechazado: 'Rechazado',
  pendiente_envio: 'Pendiente de envío',
};
