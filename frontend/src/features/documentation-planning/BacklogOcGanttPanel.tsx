import { useMemo } from 'react';
import type { components } from '../../api/generated/modulo1';
import { OcGanttChart, type GanttOcRow } from './OcGanttChart';
import { OcGanttNav } from './OcGanttNav';
import { useGanttViewport } from './useGanttViewport';
import { session } from '../../api';
import { tituloQuiebreMapa } from './ocDetail';

type BacklogItem = components['schemas']['OcBacklogItem'] & { estado_documental?: string | null };

function etiquetaOcContexto(row: BacklogItem): string {
  return [row.operadora_nombre, row.locacion_nombre, row.tipo_servicio_nombre].filter(Boolean).join(' · ');
}

function tenantTz() {
  return session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
}

function buildGanttRows(items: BacklogItem[]): GanttOcRow[] {
  return items.map(row => ({
    id: row.clave_origen,
    label: row.clave_origen,
    sublabel: etiquetaOcContexto(row),
    desde: row.vigencia_desde,
    hasta: row.vigencia_hasta,
    reprogramada: row.reprogramada,
    tramosAlerta: (row.alertas_ciertas || []).flatMap(a => (a.tramos as { desde: string; hasta: string }[] | undefined) || []).concat(
      (row.alertas_ciertas || []).filter(a => a.desde && a.hasta).map(a => ({ desde: a.desde!, hasta: a.hasta! })),
    ),
    alertas: (row.disponibilidad_por_tipo || []).flatMap(d =>
      (d.se_cae_en_ventana || []).map(s => {
        const raw = s as { fecha?: string; requisito?: string; nombre?: string };
        const fecha = typeof raw.fecha === 'string' ? raw.fecha : row.vigencia_hasta;
        return {
          fecha,
          titulo: tituloQuiebreMapa({ ...raw, fecha }, d.etiqueta, tenantTz()),
        };
      }),
    ),
  }));
}

type Props = {
  hoy: string;
  items: BacklogItem[];
  mes: string;
  selectedClave: string | null;
  onSelect: (claveOrigen: string) => void;
};

export function BacklogOcGanttPanel({ hoy, items, mes, selectedClave, onSelect }: Props) {
  const autoDesde = useMemo(() => {
    if (mes) return `${mes}-01`;
    if (!items.length) return hoy;
    return items.reduce((acc, i) => (i.vigencia_desde < acc ? i.vigencia_desde : acc), items[0].vigencia_desde);
  }, [items, mes, hoy]);

  const autoHasta = useMemo(() => {
    if (mes) {
      const [y, m] = mes.split('-').map(Number);
      const last = new Date(y, m, 0).getDate();
      return `${mes}-${String(last).padStart(2, '0')}`;
    }
    if (!items.length) return hoy;
    return items.reduce((acc, i) => (i.vigencia_hasta > acc ? i.vigencia_hasta : acc), items[0].vigencia_hasta);
  }, [items, mes, hoy]);

  const gantt = useGanttViewport({ hoy, autoDesde, autoHasta });
  const ganttRows = useMemo(() => buildGanttRows(items), [items]);

  return (
    <>
      <div className="planning-legend gantt-legend">
        <span><i className="legend-dot status-vigente" />Vigente</span>
        <span><i className="legend-dot status-por_vencer" />Por vencer</span>
        <span><i className="legend-dot status-vencido" />Sin cobertura</span>
      </div>
      <OcGanttNav
        zoom={gantt.zoom}
        onZoomChange={gantt.setZoom}
        onAnterior={gantt.anterior}
        onSiguiente={gantt.siguiente}
        onHoy={gantt.irHoy}
        modoAuto={gantt.modoAuto}
        onRestaurarAuto={gantt.usarRangoAutomatico}
      />
      <OcGanttChart
        filas={ganttRows}
        vistaDesde={gantt.vistaDesde}
        vistaHasta={gantt.vistaHasta}
        hoy={hoy}
        selectedId={selectedClave}
        onSelect={onSelect}
      />
    </>
  );
}
