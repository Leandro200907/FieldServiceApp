import { describe, expect, it } from 'vitest';
import { etiquetasEvidencia, textoPropuestaEnRevision } from '../src/ui/evidenciaPresentacion';

describe('evidenciaPresentacion', () => {
  it('separa vigencia y sin archivo de respaldo', () => {
    const labels = etiquetasEvidencia({
      estado_presentacion: 'verificada',
      estado_confirmacion: 'verificado',
      estados_adicionales: ['sin_archivo_respaldo'],
    });
    expect(labels).toEqual(['Vigente', 'Sin archivo de respaldo']);
  });

  it('prioriza por vencer sobre archivo en revisión y confirmación aparte', () => {
    const labels = etiquetasEvidencia({
      estado_presentacion: 'por_vencer',
      estado_confirmacion: 'verificado',
      estados_adicionales: ['archivo_en_revision'],
    });
    expect(labels).toEqual(['Por vencer', 'Archivo en revisión']);
  });

  it('muestra vencida e evidencia inválida', () => {
    const labels = etiquetasEvidencia({
      estado_presentacion: 'vencida',
      estado_confirmacion: 'verificado',
      estados_adicionales: ['evidencia_invalida'],
    });
    expect(labels).toEqual(['Vencida', 'Evidencia inválida']);
  });

  it('formatea aviso de propuesta en revisión', () => {
    expect(
      textoPropuestaEnRevision({
        documento_id: 'x',
        vigente_desde: '2027-01-01',
        vigente_hasta: '2027-01-31',
        estado_presentacion: 'propuesta_en_revision',
        estado_presentacion_explicacion: '',
      }),
    ).toBe('Propuesta en revisión: nueva versión hasta 31/01/2027');
  });
});
