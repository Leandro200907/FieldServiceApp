import type { ItemBandejaRevision } from './contracts';

export function nombreLegajoEnAviso(item: ItemBandejaRevision): string {
  return item.nombre_apellido || item.identificador_natural || 'la persona';
}

export function mensajeConfirmacionBandeja(item: ItemBandejaRevision): string {
  return `✓ ${item.requisito} de ${nombreLegajoEnAviso(item)} confirmada`;
}

export function mensajeRechazoBandeja(item: ItemBandejaRevision): string {
  return `Propuesta de ${nombreLegajoEnAviso(item)} rechazada`;
}

export function propuestaSinArchivoAdjunto(item: ItemBandejaRevision): boolean {
  return item.tipo_item === 'propuesta' && item.archivo_validacion === 'sin_archivo';
}

export function itemPermiteAbrirArchivo(item: ItemBandejaRevision): boolean {
  if (propuestaSinArchivoAdjunto(item)) return false;
  if (item.tipo_item === 'propuesta') return item.archivo_validacion === 'valido';
  return item.archivo_validacion !== 'invalido';
}
