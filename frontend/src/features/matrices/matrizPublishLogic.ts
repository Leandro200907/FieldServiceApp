import type { components } from '../../api/generated/modulo1';
import type { EditorLinea, MatrizDraft } from './matrizDraft';

export type PublicarLinea = {
  requisito_definicion_id: string;
  clasificacion: 'bloqueante_duro' | 'excepcionable';
  bloqueante_durante_ejecucion: boolean;
};

export type PublicarVersionBody = components['schemas']['PublicarVersionDeMatriz'];

export function lineasIncluidas(lineas: EditorLinea[]): PublicarLinea[] {
  return lineas
    .filter(l => l.incluido)
    .map(l => ({
      requisito_definicion_id: l.requisito_definicion_id,
      clasificacion: l.clasificacion,
      bloqueante_durante_ejecucion: l.bloqueante_durante_ejecucion,
    }));
}

export function buildPublicarVersionBody(draft: MatrizDraft): PublicarVersionBody {
  const lineas = lineasIncluidas(draft.lineas);
  const body: PublicarVersionBody = {
    cliente_id: draft.clienteId,
    locacion_id: draft.locacionId,
    tipo_servicio_id: draft.tipoServicioId,
    vigente_desde: draft.vigenteDesde,
    lineas,
    fuente: draft.fuente || undefined,
    archivo_de_respaldo: draft.archivoDeRespaldo || undefined,
  };
  if (draft.modo === 'plantilla' && draft.matrizGlobalId) {
    body.matriz_global_id = draft.matrizGlobalId;
  }
  return body;
}

export type ApiCallPlan = { method: 'POST'; path: '/v1/comandos/publicar_version_de_matriz'; body: PublicarVersionBody };

/** Una sola publicación por acción del usuario (plantilla incluida). */
export function planPublicarMatriz(draft: MatrizDraft): ApiCallPlan[] {
  return [{ method: 'POST', path: '/v1/comandos/publicar_version_de_matriz', body: buildPublicarVersionBody(draft) }];
}
