import { describe, expect, it } from 'vitest';
import {
  itemPermiteAbrirArchivo,
  mensajeConfirmacionBandeja,
  mensajeRechazoBandeja,
  propuestaSinArchivoAdjunto,
} from '../src/features/propuestas/bandejaMensajes';
import type { ItemBandejaRevision } from '../src/features/propuestas/contracts';

const base: ItemBandejaRevision = {
  tipo_item: 'propuesta',
  documento_id: 'd1',
  sujeto_id: 's1',
  requisito: 'Licencia de conducir',
  nombre_apellido: 'Lucía Fernández',
  identificador_natural: '30.111.224',
  archivo_validacion: 'valido',
  estado_presentacion: 'propuesta_en_revision',
  estado_presentacion_explicacion: '',
  ocs_afectadas: [],
};

describe('bandejaMensajes', () => {
  it('arma avisos breves de confirmación y rechazo', () => {
    expect(mensajeConfirmacionBandeja(base)).toBe('✓ Licencia de conducir de Lucía Fernández confirmada');
    expect(mensajeRechazoBandeja({ ...base, nombre_apellido: 'Juan Pérez' })).toBe('Propuesta de Juan Pérez rechazada');
  });

  it('detecta propuesta sin archivo y bloquea abrir', () => {
    const sin = { ...base, archivo_validacion: 'sin_archivo' as const };
    expect(propuestaSinArchivoAdjunto(sin)).toBe(true);
    expect(itemPermiteAbrirArchivo(sin)).toBe(false);
    expect(itemPermiteAbrirArchivo(base)).toBe(true);
  });
});
