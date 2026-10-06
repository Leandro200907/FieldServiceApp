import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src');

const allowTodayIso = new Set([
  path.normalize('features/documentation-planning/dates.ts'),
]);

const allowNewDate = new Set([
  path.normalize('features/documentation-planning/dates.ts'),
  path.normalize('features/documentation-planning/useGanttViewport.ts'),
  path.normalize('features/documentation-planning/BacklogOcScreen.tsx'),
  path.normalize('features/mi-legajo/validarRenovacion.ts'),
  path.normalize('features/mi-legajo/validarIncorporacion.ts'),
  path.normalize('features/legajos/validarRegistroRespaldo.ts'),
  path.normalize('features/vencimientos/temporaryMockAccess.ts'),
]);

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...await walk(full));
    else if (/\.(ts|tsx)$/.test(entry.name)) files.push(full);
  }
  return files;
}

const violations = [];
const files = await walk(root);
for (const file of files) {
  const rel = path.normalize(path.relative(root, file));
  const text = await readFile(file, 'utf8');
  if (/\btodayIso\s*\(/.test(text) && !allowTodayIso.has(rel)) {
    violations.push(`${rel}: usa todayIso() (el «hoy» de dominio viene del backend)`);
  }
  if (/\bnew\s+Date\s*\(/.test(text) && !allowNewDate.has(rel)) {
    violations.push(`${rel}: usa new Date() (permitido solo en utilidades de calendario/validación de formularios)`);
  }
}

if (violations.length) {
  console.error('Regla única frontend — violaciones:\n' + violations.map(v => `  - ${v}`).join('\n'));
  process.exit(1);
}
console.log(`Regla única frontend OK (${files.length} archivos en src/).`);
