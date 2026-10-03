import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('logout sin return', () => {
  it('marca suppressLoginReturn al cerrar sesión', () => {
    const src = readFileSync(join(process.cwd(), 'src/api/session.ts'), 'utf8');
    expect(src).toContain('suppressLoginReturn: true');
  });
});
