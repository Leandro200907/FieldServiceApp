import type { components } from '../../api/generated/modulo1';
import type { EditorLinea } from './matrizDraft';

type LineaGlobal = components['schemas']['LineaMatrizGlobal'];
type DefGlobal = components['schemas']['DefinicionGlobalConCopias'];

export function lineaEditorDesdePlantilla(lg: LineaGlobal, requisitoDefinicionId: string): EditorLinea {
  return {
    requisito_definicion_id: requisitoDefinicionId,
    nombre: lg.nombre,
    tipo_sujeto_aplicable: lg.tipo_sujeto_aplicable,
    categoria: lg.categoria,
    incluido: true,
    clasificacion: lg.clasificacion as EditorLinea['clasificacion'],
    bloqueante_durante_ejecucion: lg.bloqueante_durante_ejecucion,
  };
}

export async function prepararLineasDesdePlantilla(
  lineasGlobales: LineaGlobal[],
  locacionId: string,
  definiciones: DefGlobal[],
  copiarDefinicion: (definicionGlobalId: string, categoria: string) => Promise<string>,
): Promise<EditorLinea[]> {
  const copiasPorNombre = new Map<string, string>();
  const out: EditorLinea[] = [];
  for (const lg of lineasGlobales) {
    let rid = resolverRequisitoLocal(lg.definicion_global_id, locacionId, definiciones, copiasPorNombre);
    if (!rid) {
      rid = await copiarDefinicion(lg.definicion_global_id, lg.categoria);
      copiasPorNombre.set(lg.nombre, rid);
    }
    out.push(lineaEditorDesdePlantilla(lg, rid));
  }
  return out;
}

export function resolverRequisitoLocal(
  definicionGlobalId: string,
  locacionId: string,
  definiciones: DefGlobal[],
  copiasPorNombre: Map<string, string>,
): string | null {
  const def = definiciones.find(d => d.definicion_global_id === definicionGlobalId);
  if (!def) return null;
  const copia = def.copias_locales.find(c => (
    def.categoria === 'induccion' ? c.locacion_id === locacionId : true
  ));
  if (copia) return copia.requisito_definicion_id;
  return copiasPorNombre.get(def.nombre) ?? null;
}
