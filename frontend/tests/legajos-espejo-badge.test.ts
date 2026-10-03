import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('LegajosScreen espejo por operadora', () => {
  it('usa estados Sin presentaciones / Al día / Con diferencias', () => {
    const src = readFileSync(join(process.cwd(), 'src/features/legajos/LegajoFicha.tsx'), 'utf8');
    expect(src).toContain('Sin presentaciones registradas');
    expect(src).toContain('readEspejoOperadora');
    expect(src).not.toContain('Operadoras actualizadas');
  });
});
