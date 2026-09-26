import type { components } from '../../api/generated/modulo1';

// Tipos reales del backend — no se redeclaran a mano (mismo criterio que
// documentation-planning/contracts.ts): cualquier divergencia con el contrato real tiene
// que aparecer como error de TypeScript al regenerar, nunca como un campo "parecido".
export type MiLegajoResponse = components['schemas']['MiLegajoResponse'];
export type LegajoCompuesto = components['schemas']['app__modules__consultas__router__LegajoResponse'];
export type RecursoCustodiado = components['schemas']['RecursoCustodiado'];
export type EvidenciaVigente = components['schemas']['EvidenciaVigente'];
export type LegajoDatos = components['schemas']['LegajoDatos'];
export type ResumenLegajo = components['schemas']['ResumenLegajo'];

export interface MiLegajoAccess {
  readMiLegajo(): Promise<MiLegajoResponse>;
}
