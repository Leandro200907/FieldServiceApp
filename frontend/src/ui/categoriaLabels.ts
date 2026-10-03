const labels: Record<string, string> = {
  documento: 'Documento',
  competencia: 'Competencia',
  vehiculo: 'Vehículo',
  induccion: 'Inducción',
  acreditacion: 'Acreditación',
};

export function etiquetaCategoria(categoria: string | null | undefined): string {
  if (!categoria) return 'Sin categoría';
  return labels[categoria.toLowerCase()] ?? categoria.charAt(0).toUpperCase() + categoria.slice(1);
}
