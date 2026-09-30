import { useMemo, useState } from 'react';

export type GanttZoom = 'mes' | 'trimestre';

function parseDay(iso: string) {
  return new Date(`${iso}T12:00:00`);
}

function toIso(d: Date) {
  return d.toISOString().slice(0, 10);
}

function startOfMonth(iso: string) {
  const d = parseDay(iso);
  return toIso(new Date(d.getFullYear(), d.getMonth(), 1));
}

function endOfMonth(iso: string) {
  const d = parseDay(iso);
  return toIso(new Date(d.getFullYear(), d.getMonth() + 1, 0));
}

function startOfQuarter(iso: string) {
  const d = parseDay(iso);
  const q = Math.floor(d.getMonth() / 3) * 3;
  return toIso(new Date(d.getFullYear(), q, 1));
}

function endOfQuarter(iso: string) {
  const d = parseDay(iso);
  const q = Math.floor(d.getMonth() / 3) * 3;
  return toIso(new Date(d.getFullYear(), q + 3, 0));
}

function shiftMonths(iso: string, delta: number) {
  const d = parseDay(iso);
  d.setMonth(d.getMonth() + delta);
  return toIso(d);
}

type Options = {
  hoy: string;
  autoDesde?: string | null;
  autoHasta?: string | null;
};

export function useGanttViewport({ hoy, autoDesde, autoHasta }: Options) {
  const [modoAuto, setModoAuto] = useState(true);
  const [zoom, setZoom] = useState<GanttZoom>('mes');
  const [ancla, setAncla] = useState(hoy);

  const vista = useMemo(() => {
    if (modoAuto && autoDesde && autoHasta && autoDesde <= autoHasta) {
      return { desde: autoDesde, hasta: autoHasta };
    }
    if (zoom === 'mes') {
      return { desde: startOfMonth(ancla), hasta: endOfMonth(ancla) };
    }
    return { desde: startOfQuarter(ancla), hasta: endOfQuarter(ancla) };
  }, [modoAuto, autoDesde, autoHasta, zoom, ancla]);

  const paso = zoom === 'mes' ? 1 : 3;

  return {
    vistaDesde: vista.desde,
    vistaHasta: vista.hasta,
    zoom,
    setZoom: (z: GanttZoom) => {
      setModoAuto(false);
      setZoom(z);
    },
    anterior: () => {
      setModoAuto(false);
      setAncla(a => shiftMonths(a, -paso));
    },
    siguiente: () => {
      setModoAuto(false);
      setAncla(a => shiftMonths(a, paso));
    },
    irHoy: () => {
      setModoAuto(false);
      setAncla(hoy);
    },
    modoAuto,
    usarRangoAutomatico: () => setModoAuto(true),
  };
}
