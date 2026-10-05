import { ApiFailure, parseApiError, session } from '../../api';
import { subirArchivoEvidencia } from '../../api/evidenciaUpload';
import { createCommandIntent } from '../../api/idempotency';
import type { components } from '../../api/generated/modulo1';

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

export async function crearCertificadoRespaldo(personaId: string): Promise<string> {
  const intent = createCommandIntent('/v1/comandos/crear_certificado_respaldo', { persona_id: personaId });
  const data = await unwrap(
    session.client.POST('/v1/comandos/crear_certificado_respaldo', {
      body: { persona_id: personaId },
      headers: intent.headers,
    }),
  );
  return data.certificado_documento_id;
}

export async function asegurarCertificadoSubido(
  personaId: string,
  archivo: File,
  certificadoExistenteId: string | null,
): Promise<string> {
  const certificadoId = certificadoExistenteId ?? await crearCertificadoRespaldo(personaId);
  await subirArchivoEvidencia(certificadoId, archivo);
  return certificadoId;
}

type RegistrarInduccion = components['schemas']['RegistrarInduccion'];
type RegistrarAcreditacion = components['schemas']['RegistrarAcreditacionDeCompetencia'];

export async function registrarInduccionConCertificado(body: RegistrarInduccion): Promise<void> {
  const intent = createCommandIntent('/v1/comandos/registrar_induccion', body);
  await unwrap(
    session.client.POST('/v1/comandos/registrar_induccion', {
      body,
      headers: intent.headers,
    }),
  );
}

export async function abrirCertificadoRespaldo(documentoId: string): Promise<string> {
  const data = await unwrap(
    session.client.POST('/v1/storage/documentos/{documento_id}/url', {
      params: { path: { documento_id: documentoId } },
    }),
  );
  return data.url;
}

export async function registrarCompetenciaConCertificado(body: RegistrarAcreditacion): Promise<void> {
  const intent = createCommandIntent('/v1/comandos/registrar_acreditacion_de_competencia', body);
  await unwrap(
    session.client.POST('/v1/comandos/registrar_acreditacion_de_competencia', {
      body,
      headers: intent.headers,
    }),
  );
}
