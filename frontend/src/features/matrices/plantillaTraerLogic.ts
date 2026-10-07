import type { components } from '../../api/generated/modulo1';
import type { CambioPlantilla } from './matrizDraft';
import type { PublicarLinea } from './matrizPublishLogic';

type Copia = components['schemas']['CopiaLocalMatriz'];
type DefGlobal = components['schemas']['DefinicionGlobalConCopias'];

export function buildLineasTraerCambios(
  copia: Copia,
  _cambios: CambioPlantilla[],
  elegidos: CambioPlantilla[],
  _defsGlobales: DefGlobal[],
  requisitoPorGlobalId: Map<string, string>,
): PublicarLinea[] {
  let lineas: PublicarLinea[] = copia.lineas.map(l => ({
    requisito_definicion_id: l.requisito_definicion_id,
    clasificacion: l.clasificacion as PublicarLinea['clasificacion'],
    bloqueante_durante_ejecucion: l.bloqueante_durante_ejecucion,
  }));
  lineas = lineas.map(l => {
    const cambio = elegidos.find(c => c.requisito_definicion_id === l.requisito_definicion_id && c.clasificacion_destino);
    if (!cambio?.clasificacion_destino) return l;
    return {
      ...l,
      clasificacion: cambio.clasificacion_destino as PublicarLinea['clasificacion'],
      bloqueante_durante_ejecucion: cambio.bloqueante_durante_ejecucion_destino ?? l.bloqueante_durante_ejecucion,
    };
  }).filter(l => !elegidos.some(c => c.tipo === 'quitado' && c.requisito_definicion_id === l.requisito_definicion_id));

  for (const c of elegidos.filter(x => x.tipo === 'agregado')) {
    if (!c.definicion_global_id) continue;
    const rid = requisitoPorGlobalId.get(c.definicion_global_id);
    if (!rid || lineas.some(l => l.requisito_definicion_id === rid)) continue;
    lineas.push({
      requisito_definicion_id: rid,
      clasificacion: (c.clasificacion_destino || 'bloqueante_duro') as PublicarLinea['clasificacion'],
      bloqueante_durante_ejecucion: c.bloqueante_durante_ejecucion_destino ?? true,
    });
  }
  return lineas;
}

export function buildTraerPublicacionBody(
  copia: Copia,
  matrizGlobalId: string,
  hoy: string,
  lineas: PublicarLinea[],
  nCambios: number,
): components['schemas']['PublicarVersionDeMatriz'] {
  return {
    cliente_id: copia.cliente_id,
    locacion_id: copia.locacion_id!,
    tipo_servicio_id: copia.tipo_servicio_id,
    vigente_desde: hoy,
    matriz_global_id: matrizGlobalId,
    lineas,
    fuente: `Actualización plantilla (${nCambios} cambios)`,
  };
}

export function copiasDefinicionNecesarias(
  elegidos: CambioPlantilla[],
  defsGlobales: DefGlobal[],
  locacionId: string | null,
): components['schemas']['CopiarDefinicionGlobal'][] {
  return elegidos
    .filter(c => c.tipo === 'agregado' && c.definicion_global_id)
    .map(c => {
      const meta = defsGlobales.find(d => d.definicion_global_id === c.definicion_global_id);
      return {
        definicion_global_id: c.definicion_global_id!,
        locacion_id: meta?.categoria === 'induccion' ? locacionId : null,
      };
    });
}
