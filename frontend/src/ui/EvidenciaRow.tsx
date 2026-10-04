import { session } from '../api';
import type { EvidenciaVigente } from '../features/mi-legajo/contracts';
import { todayIso } from '../features/documentation-planning/dates';
import { etiquetasEvidencia, textoPropuestaEnRevision } from './evidenciaPresentacion';
import { StatusDot, variantFromEtiquetaVigencia } from './StatusDot';
import { formatFecha } from '../features/documentation-planning/dates';
import { formatDaysToExpiry } from './formatDaysToExpiry';
import { OcsAfectadasLine } from './OcsAfectadasLine';
import type { OcAfectadaRef } from './ocsAfectadasPresentacion';

export function EvidenciaRow({ item, hoyIso }: { item: EvidenciaVigente; hoyIso?: string }) {
  const etiquetas = etiquetasEvidencia(item);
  const hoy = hoyIso ?? todayIso();
  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const ocs = (item.ocs_afectadas ?? []) as OcAfectadaRef[];
  return (
    <li className="evidence-row">
      <span className="evidence-name">{item.requisito || 'Requisito sin nombre'}</span>
      <span className="evidence-badges estado-tags">
        {etiquetas.map(label => (
          <StatusDot key={label} variant={variantFromEtiquetaVigencia(label)}>{label}</StatusDot>
        ))}
      </span>
      <small>
        {formatFecha(item.vigente_hasta, timeZone)} · {formatDaysToExpiry(item.dias_para_vencer)}
        {(item as { observacion_operadora?: string }).observacion_operadora && (
          <> · <em>{(item as { observacion_operadora?: string }).observacion_operadora}</em></>
        )}
        {item.propuesta_en_revision && (
          <> · <em>{textoPropuestaEnRevision(item.propuesta_en_revision)}</em></>
        )}
        {ocs.length > 0 && (
          <>
            {' '}
            <OcsAfectadasLine ocs={ocs} hoyIso={hoy} timeZone={timeZone} />
          </>
        )}
      </small>
    </li>
  );
}
