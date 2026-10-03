import type { LegajoDatos } from '../mi-legajo/contracts';
import type { SujetoItem } from './contracts';

/** D14: nombre como título humano; DNI / identificador como dato secundario. */
export function tituloLegajoPersona(
  legajo: Pick<LegajoDatos | SujetoItem, 'tipo_sujeto' | 'nombre_apellido' | 'identificador_natural'>,
): string {
  if (legajo.tipo_sujeto === 'persona' && legajo.nombre_apellido) {
    return legajo.nombre_apellido;
  }
  return legajo.identificador_natural;
}

export function subtituloLegajoPersona(
  legajo: Pick<LegajoDatos | SujetoItem, 'tipo_sujeto' | 'nombre_apellido' | 'identificador_natural'>,
): string | null {
  if (legajo.tipo_sujeto === 'persona' && legajo.nombre_apellido) {
    return `DNI ${legajo.identificador_natural}`;
  }
  return null;
}
