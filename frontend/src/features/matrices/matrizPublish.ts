import { session } from '../../api';
import type { EditorLinea, MatrizDraft } from './matrizDraft';

function idem() {
  return { 'Idempotency-Key': crypto.randomUUID() };
}

type LineaPayload = { requisito_definicion_id: string; clasificacion: 'bloqueante_duro' | 'excepcionable'; bloqueante_durante_ejecucion: boolean };

function lineasPayload(lineas: EditorLinea[]): LineaPayload[] {
  return lineas
    .filter(l => l.incluido)
    .map(l => ({
      requisito_definicion_id: l.requisito_definicion_id,
      clasificacion: l.clasificacion,
      bloqueante_durante_ejecucion: l.bloqueante_durante_ejecucion,
    }));
}

function firmaLineas(lineas: LineaPayload[]): string {
  return JSON.stringify(lineas.map(l => [l.requisito_definicion_id, l.clasificacion, l.bloqueante_durante_ejecucion]).sort());
}

export async function publicarMatrizDraft(draft: MatrizDraft): Promise<void> {
  const base = {
    cliente_id: draft.clienteId,
    locacion_id: draft.locacionId,
    tipo_servicio_id: draft.tipoServicioId,
    vigente_desde: draft.vigenteDesde,
    fuente: draft.fuente || undefined,
    archivo_de_respaldo: draft.archivoDeRespaldo || undefined,
  };
  const deseadas = lineasPayload(draft.lineas);

  if (draft.modo === 'plantilla' && draft.matrizGlobalId) {
    const copia = await session.client.POST('/v1/comandos/copiar_matriz_global', {
      body: { matriz_global_id: draft.matrizGlobalId, ...base, vigente_desde: draft.vigenteDesde },
      headers: idem(),
    });
    if (copia.error || !copia.response.ok) throw new Error('No se pudo copiar la plantilla');
    const vigente = await session.client.GET('/v1/consultas/matriz_vigente', {
      params: { query: { cliente_id: draft.clienteId, locacion_id: draft.locacionId, tipo_servicio_id: draft.tipoServicioId, fecha: draft.vigenteDesde } },
    });
    const actuales: LineaPayload[] = (vigente.data?.lineas || []).map(l => ({
      requisito_definicion_id: l.requisito_definicion_id,
      clasificacion: l.clasificacion as LineaPayload['clasificacion'],
      bloqueante_durante_ejecucion: l.bloqueante_durante_ejecucion,
    }));
    if (firmaLineas(actuales) !== firmaLineas(deseadas)) {
      const pub = await session.client.POST('/v1/comandos/publicar_version_de_matriz', {
        body: { ...base, lineas: deseadas },
        headers: idem(),
      });
      if (pub.error || !pub.response.ok) throw new Error('No se pudo publicar la versión');
    }
    return;
  }

  const pub = await session.client.POST('/v1/comandos/publicar_version_de_matriz', {
    body: { ...base, lineas: deseadas },
    headers: idem(),
  });
  if (pub.error || !pub.response.ok) throw new Error('No se pudo publicar la matriz');
}
