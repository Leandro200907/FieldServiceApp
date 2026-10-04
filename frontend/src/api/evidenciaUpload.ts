import { createCommandIntent } from './idempotency';
import { ApiFailure, parseApiError, session } from './index';

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

/** Subida técnico: preparar → PUT storage → confirmar_subida (encola validacion_evidencia). */
export async function subirArchivoEvidencia(documentoId: string, archivo: File): Promise<void> {
  const contentType = archivo.type || 'application/pdf';
  const intent = createCommandIntent('/v1/comandos/preparar_subida_de_evidencia', {
    documento_id: documentoId,
    nombre_archivo: archivo.name,
    content_type: contentType,
  });
  const prep = await unwrap(session.client.POST('/v1/comandos/preparar_subida_de_evidencia', {
    body: { documento_id: documentoId, nombre_archivo: archivo.name, content_type: contentType },
    headers: intent.headers,
  }));
  const put = await fetch(prep.url_subida, { method: 'PUT', body: archivo, headers: { 'Content-Type': contentType } });
  if (!put.ok) throw new Error('No se pudo subir el archivo al almacenamiento.');
  const confIntent = createCommandIntent('/v1/comandos/confirmar_subida_de_evidencia', { documento_id: documentoId });
  await unwrap(session.client.POST('/v1/comandos/confirmar_subida_de_evidencia', {
    body: { documento_id: documentoId },
    headers: confIntent.headers,
  }));
}
