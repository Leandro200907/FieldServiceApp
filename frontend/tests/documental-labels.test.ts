import { describe, expect, it } from 'vitest';
import { labelEstadoDocumentalOc } from '../src/ui/documentalLabels';

describe('etiquetas estado documental OC', () => {
  it('traduce códigos técnicos a texto legible', () => {
    expect(labelEstadoDocumentalOc('sin_alertas_documentales')).toBe('En regla');
    expect(labelEstadoDocumentalOc('con_alertas_documentales')).toBe('Con alertas');
  });
});
