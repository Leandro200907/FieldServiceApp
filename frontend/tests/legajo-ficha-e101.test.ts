import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { variantFromEstadoFilaLegajo } from '../src/ui/StatusDot';

const fichaSrc = readFileSync(join(process.cwd(), 'src/features/legajos/LegajoFicha.tsx'), 'utf8');
const formSrc = readFileSync(join(process.cwd(), 'src/features/legajos/RegistrarRespaldoRequisitoForm.tsx'), 'utf8');

describe('E-101 ficha legajo UI', () => {
  it('usa estado_fila del backend en la columna Estado', () => {
    expect(fichaSrc).toContain('item.estado_fila');
    expect(fichaSrc).not.toMatch(/etiquetasEvidencia\(item\)/);
  });

  it('ofrece registro sin exigir faltante_exigido', () => {
    expect(fichaSrc).toContain("item.gestion_responsable === 'registrar_induccion'");
    expect(fichaSrc).not.toContain('registrar_induccion\' && item.faltante_exigido');
  });

  it('muestra Ver certificado cuando hay certificado_respaldo_documento_id', () => {
    expect(fichaSrc).toContain('Ver certificado');
    expect(fichaSrc).toContain('certificado_respaldo_documento_id');
  });

  it('ámbito usa nombre legible del payload', () => {
    expect(formSrc).toContain('item.ambito_nombre');
    expect(formSrc).toContain('item.locacion_nombre');
  });

  it('variantFromEstadoFilaLegajo distingue sin respaldo de vigente', () => {
    expect(variantFromEstadoFilaLegajo('Sin respaldo válido')).toBe('sin_respaldo');
    expect(variantFromEstadoFilaLegajo('Vigente')).toBe('vigente');
  });
});
