import { session } from '../../api';
import { Badge } from '../../ui/States';
import { formatFecha } from './dates';
import type { DetalleLegajoRadarResponse } from './contracts';
import {
  etiquetaEstadoRequisitoRadar,
  motivoFalloRequisitoRadar,
  requisitosRadarVisibles,
  textoVencimientoRequisitoRadar,
  tituloLegajoRadar,
  tonoEstadoRequisitoRadar,
  type RadarRequisitoEvaluado,
} from './radarLegajoPresentation';

const stateLabels: Record<string, string> = {
  sin_alertas_documentales: 'Sin alertas documentales',
  con_alertas_documentales: 'Con alertas documentales',
  informacion_incompleta: 'Información incompleta',
  sin_matriz: 'Sin matriz aplicable',
  fuera_de_alcance: 'Recursos fuera de tu alcance',
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function asRequisitos(value: unknown): RadarRequisitoEvaluado[] {
  if (!Array.isArray(value)) return [];
  return value.filter(item => typeof item === 'object' && item !== null) as RadarRequisitoEvaluado[];
}

export function RadarLegajoEvidenciaPanel({ data }: { data: DetalleLegajoRadarResponse }) {
  const legajo = asRecord(data.legajo);
  if (!legajo) return null;

  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const format = (iso: string) => formatFecha(iso, timeZone);
  const requisitos = requisitosRadarVisibles(asRequisitos(legajo.requisitos));
  const estadoDoc = typeof legajo.estado_documental === 'string' ? legajo.estado_documental : '';

  return (
    <section className="panel backlog-legajo-detail" aria-live="polite">
      <p className="eyebrow">Evidencia del legajo en esta OC</p>
      <h3>{tituloLegajoRadar({
        tipo_sujeto: typeof legajo.tipo_sujeto === 'string' ? legajo.tipo_sujeto : undefined,
        nombre_apellido: typeof legajo.nombre_apellido === 'string' ? legajo.nombre_apellido : null,
        identificador_natural: typeof legajo.identificador_natural === 'string' ? legajo.identificador_natural : null,
      })}</h3>
      {estadoDoc && (
        <p>
          Estado documental:{' '}
          <span className={`projection-status projection-${estadoDoc}`}>
            {stateLabels[estadoDoc] ?? estadoDoc}
          </span>
        </p>
      )}
      {requisitos.length === 0 ? (
        <p className="empty-inline">No hay requisitos evaluados para este legajo en la OC.</p>
      ) : (
        <div className="projection-table-wrap">
          <table className="projection-table radar-requisitos-table">
            <thead>
              <tr>
                <th>Requisito</th>
                <th>Estado</th>
                <th>Vencimiento</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {requisitos.map((req, index) => {
                const etiqueta = etiquetaEstadoRequisitoRadar(req);
                const motivo = motivoFalloRequisitoRadar(req);
                const key = `${req.nombre ?? 'req'}-${index}`;
                return (
                  <tr key={key}>
                    <td><strong>{req.nombre || 'Requisito sin nombre'}</strong></td>
                    <td><Badge tone={tonoEstadoRequisitoRadar(etiqueta)}>{etiqueta}</Badge></td>
                    <td>{textoVencimientoRequisitoRadar(req.vigente_hasta, format)}</td>
                    <td>{motivo ?? '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="detail-note">{data.advertencia}</p>
    </section>
  );
}
