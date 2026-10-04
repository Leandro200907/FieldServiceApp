export type PreviewMedia = 'image' | 'pdf';

export function abrirUrlDescargaAbsoluta(url: string): string {
  return url.startsWith('http') ? url : `${typeof window !== 'undefined' ? window.location.origin : ''}${url.startsWith('/') ? '' : '/'}${url}`;
}

export function tipoPreviewDesdeUrl(url: string): PreviewMedia {
  const path = url.split('?')[0].toLowerCase();
  if (path.endsWith('.pdf')) return 'pdf';
  return 'image';
}
