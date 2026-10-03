import type { components } from '../../api/generated/modulo1';
import type { EvidenciaVigente } from '../mi-legajo/contracts';

// Mismo patrón que documentation-planning/mi-legajo: tipos reales del backend, nunca
// redeclarados a mano. `TableroVencimientosResponse.items` reusa `EvidenciaVigente`, el
// mismo shape que ya consume mi-legajo (misma derivación visual, `deriveVisualState`).
export type TableroVencimientosResponse = components['schemas']['TableroVencimientosResponse'];
export type AlertasOperadoraResponse = components['schemas']['AlertasOperadoraResponse'];
export type EspejoOperadoraResponse = components['schemas']['EspejoOperadoraResponse'];
export type HistorialOperadoraResponse = components['schemas']['HistorialOperadoraResponse'];
export type ImportarPlanillaOperadorasResponse = components['schemas']['ImportarPlanillaOperadorasResponse'];
export type { EvidenciaVigente };

export interface VencimientosQuery {
  dias?: number;
  offset?: number;
  limit?: number;
}

export interface EspejoOperadoraQuery extends Pick<VencimientosQuery, 'offset' | 'limit'> {
  operadora_id?: string[];
  requisito_definicion_id?: string[];
  tipo_sujeto?: 'persona' | 'vehiculo' | 'equipo' | 'empresa';
  q?: string;
  estado_operadora?: ('pendiente_envio' | 'pendiente_aceptacion' | 'rechazado' | 'al_dia')[];
  movimiento_desde?: string;
  movimiento_hasta?: string;
  mes?: string;
}

export interface HistorialOperadoraQuery {
  operadoraId: string;
  sujetoId: string;
  requisitoDefinicionId: string;
}

export interface VencimientosAccess {
  readTableroVencimientos(query: VencimientosQuery): Promise<TableroVencimientosResponse>;
  readAlertasOperadora(query: Pick<VencimientosQuery, 'offset' | 'limit'>): Promise<AlertasOperadoraResponse>;
  readEspejoOperadora(query: EspejoOperadoraQuery): Promise<EspejoOperadoraResponse>;
  readHistorialOperadora(query: HistorialOperadoraQuery): Promise<HistorialOperadoraResponse>;
  importarPlanilla(file: File): Promise<ImportarPlanillaOperadorasResponse>;
}


