import { describe, expect, it } from 'vitest';
import {
  validarArchivoCertificado,
  validarFechaRealizacion,
  validarFechaVencimientoRespaldo,
  mensajeErrorApiRegistroRespaldo,
  MAX_BYTES_CERTIFICADO,
} from '../src/features/legajos/validarRegistroRespaldo';

describe('validarRegistroRespaldo', () => {
  it('bloquea fecha de realización futura', () => {
    expect(validarFechaRealizacion('2026-10-10', '2026-10-05')).toMatch(/futura/i);
    expect(validarFechaRealizacion('2026-10-05', '2026-10-05')).toBeNull();
  });

  it('aplica tope de 10 años al vencimiento', () => {
    expect(validarFechaVencimientoRespaldo('2036-10-06', '2026-10-05')).toMatch(/10 años/);
    expect(validarFechaVencimientoRespaldo('2027-01-01', '2026-10-05')).toBeNull();
  });

  it('rechaza archivos demasiado grandes', () => {
    const grande = { name: 'cert.pdf', type: 'application/pdf', size: MAX_BYTES_CERTIFICADO + 1 } as File;
    expect(validarArchivoCertificado(grande)).toMatch(/25 MiB/);
  });

  it('traduce códigos de error del backend', () => {
    expect(mensajeErrorApiRegistroRespaldo('x', 'respaldo_tipo_no_admitido')).toMatch(/certificado de respaldo/);
    expect(mensajeErrorApiRegistroRespaldo('x', 'prohibido', 403)).toMatch(/permiso/);
  });
});
