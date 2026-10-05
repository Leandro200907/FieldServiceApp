import type { EvidenciaVigente } from '../mi-legajo/contracts';
import { RegistrarRespaldoRequisitoForm } from './RegistrarRespaldoRequisitoForm';

export function RegistrarCompetenciaForm({
  item,
  personaId,
  hoyIso,
  onDone,
  onCancel,
}: {
  item: EvidenciaVigente;
  personaId: string;
  hoyIso: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  return (
    <RegistrarRespaldoRequisitoForm
      modo="competencia"
      item={item}
      personaId={personaId}
      hoyIso={hoyIso}
      onDone={onDone}
      onCancel={onCancel}
    />
  );
}
