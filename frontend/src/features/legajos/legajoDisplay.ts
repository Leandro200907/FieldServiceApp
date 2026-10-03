import type { LegajoDatos } from '../mi-legajo/contracts';
import type { SujetoItem } from './contracts';

/** DNI argentino con separador de miles (xx.xxx.xxx). */
export function formatDniIdentificador(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (digits.length >= 7 && digits.length <= 8) {
    const d = digits.padStart(8, '0');
    return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5)}`;
  }
  return value;
}

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
    return `DNI ${formatDniIdentificador(legajo.identificador_natural)}`;
  }
  return null;
}

/** E-26: «Nombre Apellido · DNI xx.xxx.xxx» para tablas y listas. */
export function lineaPersonaConDni(
  item: Pick<LegajoDatos | SujetoItem, 'tipo_sujeto' | 'nombre_apellido' | 'identificador_natural' | 'sujeto_id'>,
): string {
  if (item.tipo_sujeto === 'persona') {
    const nombre = item.nombre_apellido || item.identificador_natural || item.sujeto_id;
    const dni = formatDniIdentificador(item.identificador_natural || '');
    return nombre && item.nombre_apellido ? `${nombre} · DNI ${dni}` : nombre;
  }
  return item.identificador_natural || item.sujeto_id;
}
