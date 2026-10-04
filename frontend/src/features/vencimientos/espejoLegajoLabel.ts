import { lineaPersonaConDni } from '../legajos/legajoDisplay';

/** E-26: columna Legajo del espejo por operadora. */
export function espejoLegajoLabel(item: {
  tipo_sujeto: string;
  nombre_apellido?: string | null;
  identificador_natural: string;
  sujeto_id: string;
}): string {
  return lineaPersonaConDni({
    tipo_sujeto: item.tipo_sujeto,
    nombre_apellido: item.nombre_apellido ?? null,
    identificador_natural: item.identificador_natural,
    sujeto_id: item.sujeto_id,
  });
}
