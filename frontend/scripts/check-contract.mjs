import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

const expectedHash = 'aa54163d0dd78aed03df52507c2464a1c8fdf55aea2e9005285e1c166340f37b';
const bytes = await readFile(new URL('../contracts/modulo1/openapi.json', import.meta.url));
const hash = createHash('sha256').update(bytes).digest('hex');
if (hash !== expectedHash) {
  throw new Error(`OpenAPI baseline changed: expected ${expectedHash}, received ${hash}. Review the backend diff before regenerating types.`);
}
const contract = JSON.parse(bytes);
const operations = Object.values(contract.paths).reduce((total, path) => total + Object.keys(path).filter(key => ['get', 'post', 'put', 'delete', 'patch'].includes(key)).length, 0);
if (operations !== 88 || Object.keys(contract.paths).length !== 87) {
  throw new Error(`Unexpected baseline shape: ${operations} operations / ${Object.keys(contract.paths).length} paths.`);
}
console.log(`Pinned contract verified: ${operations} operations, ${Object.keys(contract.paths).length} paths, SHA-256 ${hash}.`);
