import { useState } from 'react';
import { ApiFailure } from '../../api';
import type { EvidenciaVigente } from './contracts';
import { proponerRenovacion } from './realRenovacionAccess';
import { mensajeErrorApiIncorporacion, validarFechaIncorporacion } from './validarIncorporacion';
import { session } from '../../api';

export function IncorporarDocumentoForm({
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
    const validacion = validarFechaIncorporacion(vigenteHasta, hoyIso, tz);
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
      const raw = caught instanceof ApiFailure ? caught.message : caught instanceof Error ? caught.message : 'No se pudo enviar la propuesta.';
      setError(mensajeErrorApiIncorporacion(raw));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="renovar-panel panel" role="dialog" aria-labelledby="incorporar-title">
      <h3 id="incorporar-title">Incorporar {item.requisito || 'documento'}</h3>
      <p className="muted">Requisito exigido por OC del backlog. La propuesta queda en revisión.</p>
      <div className="form-field">
        <label htmlFor="incorporar-archivo">Archivo (PDF o imagen)</label>
        <input id="incorporar-archivo" type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={e => setArchivo(e.target.files?.[0] ?? null)} />
      </div>
      <div className="form-field">
        <label htmlFor="incorporar-hasta">Fecha de vencimiento</label>
        <input id="incorporar-hasta" type="date" value={vigenteHasta} onChange={e => setVigenteHasta(e.target.value)} required />
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="proposal-actions">
        <button type="button" className="button button-primary" disabled={busy} onClick={() => void enviar()}>Enviar propuesta</button>
        <button type="button" className="button button-secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}
