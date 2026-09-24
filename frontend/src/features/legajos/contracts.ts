import type { components } from '../../api/generated/modulo1';
import type { EvidenciaVigente, LegajoCompuesto } from '../mi-legajo/contracts';

// `GET /v1/consultas/legajo` devuelve el mismo shape (hoy, legajo, documentos,
// acreditaciones, inducciones, resumen) que `MiLegajoResponse.persona`/`.recursos_bajo_custodia[]`
// — mismo schema `app__modules__consultas__router__LegajoResponse`, re-exportado acá como
// `LegajoCompuesto` (ver mi-legajo/contracts.ts). No se redeclara a mano.
export type LegajoLookupResponse = LegajoCompuesto;
export type { EvidenciaVigente };
export type SujetoItem = components['schemas']['SujetoItem'];
export type SujetosResponse = components['schemas']['SujetosResponse'];
export type SubjectKind = 'empresa' | 'persona' | 'vehiculo' | 'equipo';

export interface SujetoSearchQuery {
  q?: string;
  tipoSujeto?: SubjectKind;
  offset?: number;
  limit?: number;
}

export interface LegajosAccess {
  searchSujetos(query: SujetoSearchQuery): Promise<SujetosResponse>;
  readLegajo(sujetoId: string): Promise<LegajoLookupResponse>;
}
