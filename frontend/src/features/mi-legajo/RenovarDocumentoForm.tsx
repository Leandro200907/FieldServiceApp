import { useState } from 'react';
import { ApiFailure } from '../../api';
import type { EvidenciaVigente } from './contracts';
import { proponerRenovacion } from './realRenovacionAccess';
import { mensajeErrorApiRenovacion, validarFechaRenovacion } from './validarRenovacion';
import { formatFecha } from '../../ui/fechas';
import { session } from '../../api';

export function RenovarDocumentoForm({
  item,
  sujetoId,
  hoyIso,
  onDone,
  onCancel,
}: {
  item: EvidenciaVigente;
  sujetoId: string;
  hoyIso: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const [vigenteHasta, setVigenteHasta] = useState('');
  const [archivo, setArchivo] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar() {
    if (!archivo) {
      setError('Adjuntá un archivo (PDF o imagen).');
      return;
    }
    const validacion = validarFechaRenovacion(vigenteHasta, item.vigente_hasta, hoyIso, tz);
    if (validacion) {
      setError(validacion);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await proponerRenovacion({
        sujetoId,
        requisitoDefinicionId: item.requisito_definicion_id,
        vigenteDesde: hoyIso,
        vigenteHasta,
        archivo,
      });
      onDone();
    } catch (caught) {
      const raw = caught instanceof ApiFailure ? caught.message : caught instanceof Error ? caught.message : 'No se pudo enviar la renovación.';
      setError(mensajeErrorApiRenovacion(raw));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="renovar-panel panel" role="dialog" aria-labelledby="renovar-title">
      <h3 id="renovar-title">Renovar {item.requisito || 'documento'}</h3>
      <p className="muted">Vigente hasta {formatFecha(item.vigente_hasta, tz)}. La propuesta queda en revisión; el documento actual sigue vigente.</p>
      <div className="form-field">
        <label htmlFor="renovar-archivo">Archivo (PDF o imagen)</label>
        <input id="renovar-archivo" type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={e => setArchivo(e.target.files?.[0] ?? null)} />
      </div>
      <div className="form-field">
        <label htmlFor="renovar-hasta">Nueva fecha de vencimiento</label>
        <input id="renovar-hasta" type="date" value={vigenteHasta} onChange={e => setVigenteHasta(e.target.value)} required />
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="proposal-actions">
        <button type="button" className="button button-primary" disabled={busy} onClick={() => void enviar()}>Enviar renovación</button>
        <button type="button" className="button button-secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}
