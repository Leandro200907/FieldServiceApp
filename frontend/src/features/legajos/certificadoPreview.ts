export type PreviewMedia = 'pdf' | 'image';

export function tipoPreviewArchivo(archivo: File): PreviewMedia | null {
  const nombre = archivo.name.toLowerCase();
  if (archivo.type === 'application/pdf' || nombre.endsWith('.pdf')) return 'pdf';
  if (archivo.type.startsWith('image/') || /\.(jpe?g|png|webp)$/.test(nombre)) return 'image';
  return null;
}
