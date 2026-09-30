import { useMemo } from 'react';
import './timeline.css';

export type GanttOcRow = {
  id: string;
  label: string;
  sublabel?: string;
  desde: string;
  hasta: string;
  alertas: { fecha: string; titulo: string }[];
  tramosAlerta: { desde: string; hasta: string }[];
  reprogramada?: boolean;
};

type Props = {
  filas: GanttOcRow[];
  vistaDesde: string;
  vistaHasta: string;
  hoy?: string;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
};

function parseDay(iso: string) {
  return new Date(`${iso}T12:00:00`).getTime();
}

function pct(iso: string, min: number, max: number) {
  return ((parseDay(iso) - min) / (max - min)) * 100;
}

export function OcGanttChart({ filas, vistaDesde, vistaHasta, hoy, onSelect, selectedId }: Props) {
  const min = parseDay(vistaDesde);
  const max = parseDay(vistaHasta);
  const hoyPct = hoy ? pct(hoy, min, max) : null;

  const ticks = useMemo(() => {
    const out: string[] = [];
    const d = new Date(`${vistaDesde}T12:00:00`);
    const end = new Date(`${vistaHasta}T12:00:00`);
    while (d <= end) {
      out.push(d.toISOString().slice(0, 10));
      d.setDate(d.getDate() + Math.max(1, Math.round((end.getTime() - parseDay(vistaDesde)) / (86400000 * 8))));
    }
    return out;
  }, [vistaDesde, vistaHasta]);

  return (
    <div className="oc-gantt">
      <div className="oc-gantt-axis">
        {ticks.map(t => (
          <span key={t} style={{ left: `${pct(t, min, max)}%` }}>
            {new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: 'short' }).format(new Date(`${t}T12:00:00`))}
          </span>
        ))}
        {hoyPct != null && <div className="oc-gantt-hoy" style={{ left: `${hoyPct}%` }} title="Hoy" />}
      </div>
      {filas.map(f => {
        const left = pct(f.desde, min, max);
        const width = Math.max(0.5, pct(f.hasta, min, max) - left);
        return (
          <button
            type="button"
            key={f.id}
            className={`oc-gantt-row${selectedId === f.id ? ' selected' : ''}`}
            onClick={() => onSelect?.(f.id)}
          >
            <div className="oc-gantt-label">
              <strong>{f.label}</strong>
              {f.sublabel && <span>{f.sublabel}</span>}
              {f.reprogramada && <em className="oc-gantt-reprog">Reprogramada</em>}
            </div>
            <div className="oc-gantt-track">
              <div className="oc-gantt-bar" style={{ left: `${left}%`, width: `${width}%` }} />
              {f.tramosAlerta.map((t, i) => (
                <div
                  key={`${t.desde}-${i}`}
                  className="oc-gantt-alerta-tramo"
                  style={{
                    left: `${pct(t.desde, min, max)}%`,
                    width: `${Math.max(0.3, pct(t.hasta, min, max) - pct(t.desde, min, max))}%`,
                  }}
                />
              ))}
              {f.alertas.map((a, i) => (
                <span
                  key={`${a.fecha}-${i}`}
                  className="oc-gantt-marker"
                  style={{ left: `${pct(a.fecha, min, max)}%` }}
                  title={a.titulo}
                >
                  ▲
                </span>
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}
