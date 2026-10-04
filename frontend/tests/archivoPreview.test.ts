import { describe, expect, it } from 'vitest';
import { abrirUrlDescargaAbsoluta, tipoPreviewDesdeUrl } from '../src/features/propuestas/archivoPreview';

describe('archivoPreview', () => {
  it('absolutiza rutas relativas de storage', () => {
    expect(abrirUrlDescargaAbsoluta('/v1/storage/token')).toContain('/v1/storage/token');
    expect(abrirUrlDescargaAbsoluta('https://cdn.test/doc.pdf')).toBe('https://cdn.test/doc.pdf');
  });

  it('elige imagen o pdf para la vista previa', () => {
    expect(tipoPreviewDesdeUrl('/v1/storage/x/demo.pdf')).toBe('pdf');
    expect(tipoPreviewDesdeUrl('/v1/storage/x/foto.JPG')).toBe('image');
  });
});
