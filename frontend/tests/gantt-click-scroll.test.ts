import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

describe('OcGanttChart', () => {
  it('evita scroll al hacer clic en la barra', () => {
    const src = readFileSync(join(process.cwd(), 'src/features/documentation-planning/OcGanttChart.tsx'), 'utf8');
    expect(src).toContain('onMouseDown={event => event.preventDefault()}');
  });
});
