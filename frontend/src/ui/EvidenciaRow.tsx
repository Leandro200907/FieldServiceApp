import { session } from '../api';
import type { EvidenciaVigente } from '../features/mi-legajo/contracts';
import { todayIso } from '../features/documentation-planning/dates';
import { etiquetasEvidencia } from './evidenciaPresentacion';
import { lineasVersionYRenovacion } from './lineasEstadoEvidencia';
import { StatusDot, variantFromEtiquetaVigencia } from './StatusDot';
import { formatFecha } from '../features/documentation-planning/dates';
import { formatDaysToExpiry } from './formatDaysToExpiry';
import { OcsAfectadasLine } from './OcsAfectadasLine';
import type { OcAfectadaRef } from './ocsAfectadasPresentacion';
import type { EvidenciaVigente as EvItem } from '../features/mi-legajo/contracts';

type ItemLegajo = EvItem & {
  no_exigido_backlog?: boolean;
  gestion_tecnico?: string | null;
  faltante_exigido?: boolean;
};

export function EvidenciaRow({
  item,
  hoyIso,
  onRenovar,
  onIncorporar,
}: {
  item: ItemLegajo;
  hoyIso?: string;
  onRenovar?: (item: EvidenciaVigente) => void;
  onIncorporar?: (item: EvidenciaVigente) => void;
}) {
  const lineasRenov = lineasVersionYRenovacion(item);
  const etiquetas = lineasRenov.actual ? [] : etiquetasEvidencia(item);
  const hoy = hoyIso ?? todayIso();
  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const ocs = (item.ocs_afectadas ?? []) as OcAfectadaRef[];
  return (
    <div className="evidence-row">
      <span className="evidence-name">{item.requisito || 'Requisito sin nombre'}</span>
      <span className="evidence-badges estado-tags">
        {lineasRenov.actual ? (
          <StatusDot variant="revision">{lineasRenov.actual}</StatusDot>
        ) : etiquetas.map(label => (
          <StatusDot key={label} variant={variantFromEtiquetaVigencia(label)}>{label}</StatusDot>
        ))}
      </span>
      <small>
        {item.estado_presentacion === 'sin_documento'
          ? 'Sin documento'
          : `${formatFecha(item.vigente_hasta, timeZone)} · ${formatDaysToExpiry(item.dias_para_vencer)}`}
        {item.no_exigido_backlog && <> · <em>No exigido por OC actuales</em></>}
        {(item as { observacion_operadora?: string }).observacion_operadora && (
          <> · <em>{(item as { observacion_operadora?: string }).observacion_operadora}</em></>
        )}
        {lineasRenov.renovacion && (
          <> · <em>{lineasRenov.renovacion}</em></>
        )}
        {item.ultimo_rechazo_propuesta?.motivo && (
          <> · <em className="rechazo-motivo">Rechazada: {item.ultimo_rechazo_propuesta.motivo}</em></>
        )}
        {item.motivo_archivo_invalido && (
          <> · <em className="rechazo-motivo">{item.motivo_archivo_invalido}</em></>
        )}
        {ocs.length > 0 && (
          <>
            {' '}
            <OcsAfectadasLine ocs={ocs} hoyIso={hoy} timeZone={timeZone} />
          </>
        )}
      </small>
      {onIncorporar && item.gestion_tecnico === 'incorporar' && item.faltante_exigido && (
        <button type="button" className="button button-secondary button-small" onClick={() => onIncorporar(item)}>
          Incorporar
        </button>
      )}
      {item.gestion_tecnico === 'solo_responsable' && item.faltante_exigido && (
        <span className="muted legajo-gestion-responsable">Lo registra el responsable</span>
      )}
      {onRenovar
        && !item.propuesta_en_revision
        && !item.faltante_exigido
        && !String(item.id).startsWith('exigido-')
        && (item.estado_presentacion === 'por_vencer' || item.vencido)
        && (
          <button type="button" className="button button-secondary button-small" onClick={() => onRenovar(item)}>
            Renovar
          </button>
        )}
    </div>
  );
}
