import { session } from '../../api';
import { ApiFailure, parseApiError } from '../../api/errors';
import type { components } from '../../api/generated/modulo1';
import type { CambioPlantilla } from './matrizDraft';
import { copiarDefinicionGlobal } from './matrizApi';
import {
  buildLineasTraerCambios,
  buildTraerPublicacionBody,
  copiasDefinicionNecesarias,
} from './plantillaTraerLogic';

type Copia = components['schemas']['CopiaLocalMatriz'];

export async function ejecutarTraerCambiosPlantilla(
  copia: Copia,
  matrizGlobalId: string,
  cambios: CambioPlantilla[],
  elegidos: CambioPlantilla[],
  defsGlobales: components['schemas']['DefinicionGlobalConCopias'][],
  hoy: string,
): Promise<void> {
  const post = (path: string, init: { body: unknown; headers: Record<string, string> }) =>
    session.client.POST(path as '/v1/comandos/copiar_definicion_global', init as never);

  const requisitoPorGlobalId = new Map<string, string>();
  for (const body of copiasDefinicionNecesarias(elegidos, defsGlobales, copia.locacion_id)) {
    const rid = await copiarDefinicionGlobal(post, body);
    requisitoPorGlobalId.set(body.definicion_global_id, rid);
  }
  const lineas = buildLineasTraerCambios(copia, cambios, elegidos, defsGlobales, requisitoPorGlobalId);
  const pubBody = buildTraerPublicacionBody(copia, matrizGlobalId, hoy, lineas, elegidos.length);
  const requestId = crypto.randomUUID();
  const pub = await session.client.POST('/v1/comandos/publicar_version_de_matriz', {
    body: pubBody,
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  });
  if (pub.error !== undefined || !pub.response.ok) {
    throw new ApiFailure(parseApiError(pub.error, pub.response, requestId));
  }
}
