import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const formSrc = readFileSync(join(process.cwd(), 'src/features/legajos/RegistrarRespaldoRequisitoForm.tsx'), 'utf8');
const fichaSrc = readFileSync(join(process.cwd(), 'src/features/legajos/LegajoFicha.tsx'), 'utf8');
const apiSrc = readFileSync(join(process.cwd(), 'src/features/legajos/certificadoRespaldoApi.ts'), 'utf8');

describe('E-97 registro con certificado propio', () => {
  it('exige vista previa antes de habilitar Registrar', () => {
    expect(formSrc).toContain('bandeja-preview');
    expect(formSrc).toContain('disabled={!puedeRegistrar}');
    expect(formSrc).toMatch(/previewUrl/);
  });

  it('no envía estado_confirmacion en el registro', () => {
    expect(formSrc).not.toContain('estado_confirmacion');
    expect(apiSrc).toContain('certificado_documento_id');
  });

  it('reintenta el registro reutilizando el certificado subido', () => {
    expect(formSrc).toContain('certificadoDocumentoId');
    expect(formSrc).toContain('asegurarCertificadoSubido');
    expect(apiSrc).toMatch(/certificadoExistenteId/);
  });

  it('muestra Registrar competencia solo con gestion_responsable registrar_acreditacion', () => {
    expect(fichaSrc).toContain("item.gestion_responsable === 'registrar_acreditacion'");
    expect(fichaSrc).toContain('Registrar competencia');
    expect(fichaSrc).toContain('RegistrarCompetenciaForm');
  });
});
