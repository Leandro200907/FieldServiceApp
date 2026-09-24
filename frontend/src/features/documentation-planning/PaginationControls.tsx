// F-06 (auditoría externa 2026-09-22): ni el calendario ni el backlog pasaban nunca
// `offset`/`limit`, y ninguna pantalla comparaba `total` contra la cantidad de ítems
// mostrados — con el default de 50 del backend, un tenant con más filas quedaba
// recortado en silencio (`total` viaja en la respuesta, nunca se leía). Componente
// compartido: misma UI de "Mostrando X–Y de Z" + Anterior/Siguiente en las dos pantallas.
export const PAGE_SIZE = 50;

export function PaginationControls({
  offset, limit, total, onOffsetChange,
}: { offset: number; limit: number; total: number; onOffsetChange: (offset: number) => void }) {
  if (total <= limit && offset === 0) return null;
  const desde = total === 0 ? 0 : offset + 1;
  const hasta = Math.min(offset + limit, total);
  return <div className="pagination-controls" role="navigation" aria-label="Paginación">
    <span>Mostrando {desde}–{hasta} de {total}</span>
    <div className="pagination-buttons">
      <button className="button button-secondary" disabled={offset === 0} onClick={() => onOffsetChange(Math.max(0, offset - limit))}>← Anterior</button>
      <button className="button button-secondary" disabled={offset + limit >= total} onClick={() => onOffsetChange(offset + limit)}>Siguiente →</button>
    </div>
  </div>;
}
