import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('PropuestasScreen rechazo', () => {
  it('deshabilita confirmar rechazo sin motivo', () => {
    const src = readFileSync(join(process.cwd(), 'src/features/propuestas/PropuestasScreen.tsx'), 'utf8');
    expect(src).toContain('disabled={busy || readOnly || !motivo.trim()}');
  });

  it('muestra aviso tras confirmar o rechazar', () => {
    const src = readFileSync(join(process.cwd(), 'src/features/propuestas/PropuestasScreen.tsx'), 'utf8');
    expect(src).toContain('bandeja-aviso');
    expect(src).toContain('onAccionExitosa');
  });
});
