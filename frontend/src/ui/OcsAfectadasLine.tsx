import { useState } from 'react';
import type { OcAfectadaRef } from './ocsAfectadasPresentacion';
import { resumenOcsAfectadas } from './ocsAfectadasPresentacion';

type Props = {
  ocs: OcAfectadaRef[];
  hoyIso: string;
  timeZone: string;
};

export function OcsAfectadasLine({ ocs, hoyIso, timeZone }: Props) {
  const [expandido, setExpandido] = useState(false);
  const datos = resumenOcsAfectadas(ocs, hoyIso, timeZone);
  if (!datos) return null;
  const tieneMas = datos.tituloCompleto.length > datos.resumen.length;
  return (
    <small className="ocs-afectadas-line">
      <button
        type="button"
        className="text-button ocs-afectadas-trigger"
        title={datos.tituloCompleto}
        aria-expanded={expandido}
        onClick={() => setExpandido(v => !v)}
      >
        {expandido && tieneMas ? datos.tituloCompleto : datos.resumen}
      </button>
    </small>
  );
}
