import { useEffect, useState } from 'react';
import { ApiFailure, safeFailure } from '../../api';
import { ErrorState, LoadingState } from '../../ui/States';
import { session } from '../../api';
import { formatFecha, formatFechaHora } from '../documentation-planning/dates';
import { vencimientosAccess } from './access';
import type { HistorialOperadoraResponse } from './contracts';
import { ESTADO_HISTORIAL_LABELS } from './importacionUi';

type Props = {
  operadoraId: string;
  sujetoId: string;
  requisitoDefinicionId: string;
  onClose?: () => void;
  tituloExtra?: string;
  embedded?: boolean;
};

export function HistorialOperadoraPanel({ operadoraId, sujetoId, requisitoDefinicionId, onClose, tituloExtra, embedded }: Props) {
  const [data, setData] = useState<HistorialOperadoraResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof safeFailure> | null>(null);
  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const fmt = (value: string) => formatFecha(value, timeZone);
  const fmtPaso = (value: string) => formatFechaHora(value, timeZone);
  const estadoLabel = (estado: string) => ESTADO_HISTORIAL_LABELS[estado] || estado;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void vencimientosAccess()
      .readHistorialOperadora({ operadoraId, sujetoId, requisitoDefinicionId })
      .then(result => { if (!cancelled) setData(result); })
      .catch(err => { if (!cancelled) setError(safeFailure(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [operadoraId, sujetoId, requisitoDefinicionId]);

  const Wrapper = embedded ? 'section' : 'div';
  return (
    <Wrapper className={`panel historial-operadora-panel${embedded ? ' historial-operadora-panel--embedded' : ''}`} role={embedded ? undefined : 'dialog'} aria-labelledby="historial-operadora-title">
      <div className="panel-top">
        <div>
          {!embedded && <p className="eyebrow">Presentaciones a operadoras</p>}
          <h3 id="historial-operadora-title">{tituloExtra || 'Historial de presentaciones'}</h3>
        </div>
        {onClose && <button type="button" className="button button-secondary" onClick={onClose}>Cerrar</button>}
      </div>
      {loading ? <LoadingState /> : error ? <ErrorState message={error.message} /> : data?.versiones.length ? (
        <div className="historial-versiones">
          {data.versiones.map(version => (
            <section key={version.documento_id} className="historial-version">
              <header>
                <strong>Versión {fmt(version.vigente_desde)}</strong>
                <span className="muted"> → {fmt(version.vigente_hasta)}</span>
              </header>
              <ol className="historial-pasos">
                {version.pasos.map((paso, index) => (
                  <li key={`${paso.paso_en}-${index}`}>
                    <strong>{estadoLabel(paso.estado)}</strong> · {fmtPaso(paso.paso_en)}
                    {paso.observacion ? <p>{paso.observacion}</p> : null}
                    <p className="muted">
                      {paso.registrado_nombre}
                      {paso.origen === 'planilla' && paso.fuente_archivo
                        ? ` · ${paso.fuente_archivo}${paso.fuente_hoja ? ` / ${paso.fuente_hoja}` : ''}${paso.fuente_fila ? ` fila ${paso.fuente_fila}` : ''}`
                        : paso.origen === 'manual' ? ' · manual' : ''}
                    </p>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      ) : <p className="empty-inline">Sin movimientos registrados para este legajo y operadora.</p>}
    </Wrapper>
  );
}
