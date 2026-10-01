import { useMemo } from 'react';
import { axisTicks, clipSegment, dayPosition, formatTick, inVista } from './dates';
import './timeline.css';

export type GanttBandaOc = {
  desde: string;
  hasta: string;
  label?: string;
  filtrada?: boolean;
};

export type GanttOcRow = {
  id: string;
  label: string;
  sublabel?: string;
  desde: string;
  hasta: string;
  alertas: { fecha: string; titulo: string }[];
  tramosAlerta: { desde: string; hasta: string }[];
  reprogramada?: boolean;
  bandasOc?: GanttBandaOc[];
  barTone?: 'default' | 'vigente' | 'por_vencer' | 'vencido' | 'declarado_sin_verificar';
  indent?: number;
  ocultarBarra?: boolean;
};

type Props = {
  filas: GanttOcRow[];
  vistaDesde: string;
  vistaHasta: string;
  hoy?: string;
  onSelect?: (id: string) => void;
  selectedId?: string | null;
};

export function OcGanttChart({ filas, vistaDesde, vistaHasta, hoy, onSelect, selectedId }: Props) {
  const hoyEnVista = Boolean(hoy && inVista(hoy, vistaDesde, vistaHasta));
  const hoyPct = hoyEnVista && hoy ? dayPosition(hoy, vistaDesde, vistaHasta) : null;

  const ticks = useMemo(() => axisTicks(vistaDesde, vistaHasta), [vistaDesde, vistaHasta]);

  return (
    <div className="oc-gantt">
      <div className="oc-gantt-chart">
        <div className="oc-gantt-labels-col">
          <div className="oc-gantt-label oc-gantt-label-axis" aria-hidden="true" />
          {filas.map(f => (
            <div key={f.id} className={`oc-gantt-label${selectedId === f.id ? ' selected' : ''}`} style={f.indent ? { paddingLeft: `${8 + f.indent * 16}px` } : undefined}>
              <strong>{f.label}</strong>
              {(f.sublabel || f.reprogramada) && (
                <span>
                  {f.sublabel}
                  {f.sublabel && f.reprogramada ? ' · ' : ''}
                  {f.reprogramada && <em className="oc-gantt-reprog">Reprogramada</em>}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="oc-gantt-plots">
          <div className="oc-gantt-axis-track">
            {ticks.map((t, i) => (
              <span key={t} style={{ left: `${dayPosition(t, vistaDesde, vistaHasta)}%` }}>
                {formatTick(t, i > 0 ? ticks[i - 1] : null)}
              </span>
            ))}
          </div>
          {hoyEnVista && hoyPct != null && <div className="oc-gantt-hoy" style={{ left: `${hoyPct}%` }} title="Hoy" />}
          {filas.map(f => {
            const barra = clipSegment(f.desde, f.hasta, vistaDesde, vistaHasta);
            const barClass = f.barTone && f.barTone !== 'default' ? ` oc-gantt-bar-${f.barTone}` : '';
            return (
              <button
                type="button"
                key={f.id}
                className={`oc-gantt-track${selectedId === f.id ? ' selected' : ''}`}
                onClick={() => onSelect?.(f.id)}
              >
                {(f.bandasOc || []).map((b, i) => {
                  const seg = clipSegment(b.desde, b.hasta, vistaDesde, vistaHasta);
                  if (!seg) return null;
                  return (
                    <div
                      key={`${b.desde}-${i}`}
                      className={`oc-gantt-banda-oc${b.filtrada ? ' filtrada' : ''}`}
                      style={{ left: `${seg.left}%`, width: `${Math.max(seg.width, 0.3)}%` }}
                      title={b.label}
                    />
                  );
                })}
                {!f.ocultarBarra && barra && (
                  <div className={`oc-gantt-bar${barClass}`} style={{ left: `${barra.left}%`, width: `${Math.max(barra.width, 0.5)}%` }} />
                )}
                {f.tramosAlerta.map((t, i) => {
                  const seg = clipSegment(t.desde, t.hasta, vistaDesde, vistaHasta);
                  if (!seg) return null;
                  return (
                    <div
                      key={`${t.desde}-${i}`}
                      className="oc-gantt-alerta-tramo"
                      style={{ left: `${seg.left}%`, width: `${Math.max(seg.width, 0.3)}%` }}
                    />
                  );
                })}
                {f.alertas.filter(a => inVista(a.fecha, vistaDesde, vistaHasta)).map((a, i) => (
                  <span
                    key={`${a.fecha}-${i}`}
                    className="oc-gantt-marker"
                    style={{ left: `${dayPosition(a.fecha, vistaDesde, vistaHasta)}%` }}
                    title={a.titulo}
                  >
                    ▲
                  </span>
                ))}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
