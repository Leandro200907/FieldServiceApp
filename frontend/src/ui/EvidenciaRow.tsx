import type { EvidenciaVigente } from '../features/mi-legajo/contracts';
import { Badge } from './States';
import { etiquetasEvidencia, textoPropuestaEnRevision, tonoEvidencia } from './evidenciaPresentacion';
import { formatDaysToExpiry } from './formatDaysToExpiry';

export function EvidenciaRow({ item }: { item: EvidenciaVigente }) {
  const etiquetas = etiquetasEvidencia(item);
  return (
    <li className="evidence-row">
      <span className="evidence-name">{item.requisito || 'Requisito sin nombre'}</span>
      <span className="evidence-badges">
        {etiquetas.map(label => (
          <Badge key={label} tone={tonoEvidencia(item)}>{label}</Badge>
        ))}
      </span>
      <small>
        {item.vigente_hasta} · {formatDaysToExpiry(item.dias_para_vencer)}
        {item.propuesta_en_revision && (
          <> · <em>{textoPropuestaEnRevision(item.propuesta_en_revision)}</em></>
        )}
      </small>
    </li>
  );
}
