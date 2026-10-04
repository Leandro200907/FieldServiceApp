import { ApiFailure, parseApiError, session } from '../../api';
import { createCommandIntent } from '../../api/idempotency';
import { subirArchivoEvidencia } from '../../api/evidenciaUpload';
import type { components } from '../../api/generated/modulo1';

export type DocumentoCargadoResponse = components['schemas']['DocumentoCargadoResponse'];

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

export async function proponerRenovacion(input: {
  sujetoId: string;
  requisitoDefinicionId: string;
  vigenteDesde: string;
  vigenteHasta: string;
  archivo: File;
}): Promise<DocumentoCargadoResponse> {
  const intent = createCommandIntent('/v1/comandos/proponer_documento', {
    sujeto_id: input.sujetoId,
    requisito_definicion_id: input.requisitoDefinicionId,
    vigente_desde: input.vigenteDesde,
    vigente_hasta: input.vigenteHasta,
    origen: 'carga_manual',
  });
  const propuesta = await unwrap(session.client.POST('/v1/comandos/proponer_documento', {
    body: {
      sujeto_id: input.sujetoId,
      requisito_definicion_id: input.requisitoDefinicionId,
      vigente_desde: input.vigenteDesde,
      vigente_hasta: input.vigenteHasta,
      origen: 'carga_manual',
    },
    headers: intent.headers,
  }));
  await subirArchivoEvidencia(propuesta.documento_id, input.archivo);
  return propuesta;
}
