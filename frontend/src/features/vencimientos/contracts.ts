import type { components } from '../../api/generated/modulo1';
import type { EvidenciaVigente } from '../mi-legajo/contracts';

// Mismo patrón que documentation-planning/mi-legajo: tipos reales del backend, nunca
// redeclarados a mano. `TableroVencimientosResponse.items` reusa `EvidenciaVigente`, el
// mismo shape que ya consume mi-legajo (misma derivación visual, `deriveVisualState`).
export type TableroVencimientosResponse = components['schemas']['TableroVencimientosResponse'];
export type { EvidenciaVigente };

export interface VencimientosQuery {
  dias?: number;
  offset?: number;
  limit?: number;
}

export interface VencimientosAccess {
  readTableroVencimientos(query: VencimientosQuery): Promise<TableroVencimientosResponse>;
}
