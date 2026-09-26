import type { components } from '../../api/generated/modulo1';

export type MatrizItem = components['schemas']['MatrizItem'];
export type MatricesResponse = components['schemas']['MatricesResponse'];
export type LineaMatrizVigente = components['schemas']['LineaMatrizVigente'];
export type MatrizVigenteResponse = components['schemas']['MatrizVigenteResponse'];

export interface MatricesQuery {
  clienteId?: string;
  soloVigentes?: boolean;
  offset?: number;
  limit?: number;
}

export interface MatrizVigenteQuery {
  clienteId: string;
  locacionId: string;
  tipoServicioId: string;
  fecha?: string;
}

export interface MatricesAccess {
  readMatrices(query: MatricesQuery): Promise<MatricesResponse>;
  readMatrizVigente(query: MatrizVigenteQuery): Promise<MatrizVigenteResponse>;
}
