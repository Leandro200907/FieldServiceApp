import type { GanttZoom } from './useGanttViewport';

type Props = {
  zoom: GanttZoom;
  onZoomChange: (z: GanttZoom) => void;
  onAnterior: () => void;
  onSiguiente: () => void;
  onHoy: () => void;
  modoAuto?: boolean;
  onRestaurarAuto?: () => void;
};

export function OcGanttNav({ zoom, onZoomChange, onAnterior, onSiguiente, onHoy, modoAuto, onRestaurarAuto }: Props) {
  return (
    <div className="oc-gantt-nav" role="toolbar" aria-label="Navegación del diagrama temporal">
      <button type="button" className="button button-secondary" onClick={onAnterior}>← Anterior</button>
      <button type="button" className="button button-secondary" onClick={onSiguiente}>Siguiente →</button>
      <button type="button" className="button button-secondary" onClick={onHoy}>Hoy</button>
      <label className="oc-gantt-zoom">
        Zoom
        <select value={zoom} onChange={e => onZoomChange(e.target.value as GanttZoom)}>
          <option value="mes">Mes</option>
          <option value="trimestre">Trimestre</option>
        </select>
      </label>
      {!modoAuto && onRestaurarAuto && (
        <button type="button" className="button button-secondary" onClick={onRestaurarAuto}>Ajustar a datos</button>
      )}
    </div>
  );
}
