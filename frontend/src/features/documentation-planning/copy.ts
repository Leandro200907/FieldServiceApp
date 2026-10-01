import { formatFecha } from './dates';

export function textoEfectoAccion(efecto: string): string {
  return efecto.replace(/cobertura documental/gi, 'disponibilidad documental');
}

export function textoAccionSugerida(accion: string, fecha: string | null | undefined, timeZone: string): string {
  if (!fecha) return accion;
  return `${accion} ${formatFecha(fecha, timeZone)}`.trim();
}
