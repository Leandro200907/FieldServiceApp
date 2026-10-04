import type { components } from '../../api/generated/modulo1';

// Tipos reales del backend — no se redeclaran a mano (mismo patrón que el resto de
// features). `DocumentoPropuesto` ya trae `dias_para_vencer`/`vencido`/`vigente_hoy`
// (misma augmentación `_con_vigencia` que `EvidenciaVigente`).
export type DocumentoPropuesto = components['schemas']['DocumentoPropuesto'];
export type PropuestasPendientesResponse = components['schemas']['PropuestasPendientesResponse'];
export type ConfirmarDocumentoResponse = components['schemas']['ConfirmarDocumentoResponse'];
export type RechazarPropuestaResponse = components['schemas']['RechazarPropuestaResponse'];
export type BandejaRevisionResponse = components['schemas']['BandejaRevisionResponse'];
export type ItemBandejaRevision = components['schemas']['ItemBandejaRevision'];
export type UrlDeDescargaResponse = components['schemas']['UrlDeDescargaResponse'];

export type PestanaBandeja = 'todos' | 'propuestas' | 'archivos';

export interface PropuestasQuery {
  offset?: number;
  limit?: number;
  pestana?: PestanaBandeja;
}

export interface PropuestasAccess {
  readPropuestasPendientes(query: PropuestasQuery): Promise<PropuestasPendientesResponse>;
  readBandejaRevision(query: PropuestasQuery): Promise<BandejaRevisionResponse>;
  abrirArchivo(documentoId: string): Promise<UrlDeDescargaResponse>;
  confirmarDocumento(documentoId: string, idempotencyKey?: string): Promise<ConfirmarDocumentoResponse>;
  rechazarPropuesta(documentoId: string, motivo: string, idempotencyKey?: string): Promise<RechazarPropuestaResponse>;
}

