export const tipoSujetoLabels: Record<string, string> = {
  persona: 'Personas',
  personas: 'Personas',
  vehiculo: 'Vehículos',
  vehiculos: 'Vehículos',
  equipo: 'Equipos',
  equipos: 'Equipos',
  empresa: 'Empresa',
};

export function etiquetaTipoSujeto(tipo: string, cantidad?: number): string {
  const base = tipoSujetoLabels[tipo] ?? tipo;
  if (cantidad === undefined) return base;
  if (cantidad === 1 && base === 'Empresa') return 'Empresa (1)';
  if (cantidad === 1) return `${base.replace(/s$/, '')} (1)`;
  return `${base} (${cantidad})`;
}
