import { useState } from 'react';
import { ApiFailure, parseApiError, session } from '../../api';
import { createCommandIntent } from '../../api/idempotency';
import type { EvidenciaVigente } from '../mi-legajo/contracts';

async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

export function RegistrarInduccionForm({
  item,
  personaId,
  documentosEvidencia,
  hoyIso,
  onDone,
  onCancel,
}: {
  item: EvidenciaVigente;
  personaId: string;
  documentosEvidencia: EvidenciaVigente[];
  hoyIso: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [vigenteHasta, setVigenteHasta] = useState('');
  const [evidenciaId, setEvidenciaId] = useState(documentosEvidencia[0]?.id ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function enviar() {
    if (!item.locacion_id) {
      setError('Falta locación en la definición del requisito.');
      return;
    }
    if (!evidenciaId) {
      setError('Elegí un documento de respaldo del legajo.');
      return;
    }
    if (!vigenteHasta) {
      setError('Elegí la fecha de vencimiento.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const intent = createCommandIntent('/v1/comandos/registrar_induccion', {
        persona_id: personaId,
        locacion_id: item.locacion_id,
        requisito_definicion_id: item.requisito_definicion_id,
        vigente_desde: hoyIso,
        vigente_hasta: vigenteHasta,
        evidencia: evidenciaId,
        estado_confirmacion: 'verificado',
      });
      await unwrap(
        session.client.POST('/v1/comandos/registrar_induccion', {
          body: {
            persona_id: personaId,
            locacion_id: item.locacion_id,
            requisito_definicion_id: item.requisito_definicion_id,
            vigente_desde: hoyIso,
            vigente_hasta: vigenteHasta,
            evidencia: evidenciaId,
            estado_confirmacion: 'verificado',
          },
          headers: intent.headers,
        }),
      );
      onDone();
    } catch (caught) {
      setError(caught instanceof ApiFailure ? caught.message : 'No se pudo registrar la inducción.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="renovar-panel panel" role="dialog">
      <h3>Registrar {item.requisito || 'inducción'}</h3>
      <div className="form-field">
        <label htmlFor="ind-evidencia">Documento de respaldo</label>
        <select id="ind-evidencia" value={evidenciaId} onChange={e => setEvidenciaId(e.target.value)}>
          {documentosEvidencia.map(d => (
            <option key={d.id} value={d.id}>{d.requisito || d.id}</option>
          ))}
        </select>
      </div>
      <div className="form-field">
        <label htmlFor="ind-hasta">Vigente hasta</label>
        <input id="ind-hasta" type="date" value={vigenteHasta} onChange={e => setVigenteHasta(e.target.value)} />
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="proposal-actions">
        <button type="button" className="button button-primary" disabled={busy} onClick={() => void enviar()}>Registrar</button>
        <button type="button" className="button button-secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}
