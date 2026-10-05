import { useEffect, useMemo, useState } from 'react';
import { ApiFailure } from '../../api';
import type { EvidenciaVigente } from '../mi-legajo/contracts';
import {
  asegurarCertificadoSubido,
  registrarCompetenciaConCertificado,
  registrarInduccionConCertificado,
} from './certificadoRespaldoApi';
import { tipoPreviewArchivo } from './certificadoPreview';
import {
  mensajeErrorApiRegistroRespaldo,
  validarArchivoCertificado,
  validarFechaRealizacion,
  validarFechaVencimientoRespaldo,
} from './validarRegistroRespaldo';

export type ModoRespaldoRequisito = 'induccion' | 'competencia';

export function RegistrarRespaldoRequisitoForm({
  modo,
  item,
  personaId,
  hoyIso,
  onDone,
  onCancel,
}: {
  modo: ModoRespaldoRequisito;
  item: EvidenciaVigente;
  personaId: string;
  hoyIso: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [certificadoDocumentoId, setCertificadoDocumentoId] = useState<string | null>(null);
  const [vigenteDesde, setVigenteDesde] = useState('');
  const [vigenteHasta, setVigenteHasta] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tituloAccion = modo === 'induccion' ? 'Registrar inducción' : 'Registrar competencia';
  const previewTipo = archivo ? tipoPreviewArchivo(archivo) : null;

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const erroresFecha = useMemo(() => {
    const desde = validarFechaRealizacion(vigenteDesde, hoyIso);
    const hasta = validarFechaVencimientoRespaldo(vigenteHasta, hoyIso);
    return { desde, hasta };
  }, [vigenteDesde, vigenteHasta, hoyIso]);

  const puedeRegistrar = Boolean(
    archivo
    && previewUrl
    && previewTipo
    && !erroresFecha.desde
    && !erroresFecha.hasta
    && !busy,
  );

  function onElegirArchivo(file: File | null) {
    setError(null);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    if (!file) {
      setArchivo(null);
      return;
    }
    const validacion = validarArchivoCertificado(file);
    if (validacion) {
      setArchivo(null);
      setError(validacion);
      return;
    }
    const tipo = tipoPreviewArchivo(file);
    if (!tipo) {
      setArchivo(null);
      setError('El archivo tiene que ser PDF, JPEG, PNG o WebP.');
      return;
    }
    setArchivo(file);
    setPreviewUrl(URL.createObjectURL(file));
  }

  async function enviar() {
    if (!archivo || !item.requisito_definicion_id) return;
    if (modo === 'induccion' && !item.locacion_id) {
      setError('Falta locación en la definición del requisito.');
      return;
    }
    const errDesde = validarFechaRealizacion(vigenteDesde, hoyIso);
    const errHasta = validarFechaVencimientoRespaldo(vigenteHasta, hoyIso);
    if (errDesde || errHasta) {
      setError(errDesde || errHasta);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const certId = await asegurarCertificadoSubido(personaId, archivo, certificadoDocumentoId);
      setCertificadoDocumentoId(certId);
      if (modo === 'induccion') {
        await registrarInduccionConCertificado({
          persona_id: personaId,
          locacion_id: item.locacion_id as string,
          requisito_definicion_id: item.requisito_definicion_id,
          vigente_desde: vigenteDesde,
          vigente_hasta: vigenteHasta,
          certificado_documento_id: certId,
        });
      } else {
        await registrarCompetenciaConCertificado({
          persona_id: personaId,
          requisito_definicion_id: item.requisito_definicion_id,
          vigente_desde: vigenteDesde,
          vigente_hasta: vigenteHasta,
          certificado_documento_id: certId,
        });
      }
      onDone();
    } catch (caught) {
      if (caught instanceof ApiFailure) {
        setError(mensajeErrorApiRegistroRespaldo(caught.message, caught.detail.code, caught.detail.status));
      } else {
        setError(caught instanceof Error ? caught.message : `No se pudo ${tituloAccion.toLowerCase()}.`);
      }
    } finally {
      setBusy(false);
    }
  }

  const ambitoInduccion = item.locacion_id
    ? `Locación del requisito (${item.locacion_id})`
    : 'Sin locación en el requisito';

  return (
    <div className="renovar-panel panel" role="dialog" aria-labelledby="respaldo-requisito-title">
      <h3 id="respaldo-requisito-title">{tituloAccion}: {item.requisito || 'requisito'}</h3>
      {modo === 'induccion' && (
        <div className="form-field">
          <label>Ámbito (solo lectura)</label>
          <input type="text" readOnly value={ambitoInduccion} aria-readonly="true" />
        </div>
      )}
      <div className="form-field">
        <label htmlFor="respaldo-certificado">Certificado (PDF o imagen, máx. 25 MiB)</label>
        <input
          id="respaldo-certificado"
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/webp"
          disabled={busy}
          onChange={e => onElegirArchivo(e.target.files?.[0] ?? null)}
        />
        {certificadoDocumentoId && (
          <small className="muted">Certificado ya subido: podés corregir fechas y volver a registrar sin subir de nuevo.</small>
        )}
      </div>
      <div className="bandeja-preview" aria-label="Vista previa del certificado">
        {previewUrl && previewTipo === 'pdf' ? (
          <iframe title="Vista previa del certificado" src={previewUrl} className="bandeja-preview-media" />
        ) : previewUrl && previewTipo === 'image' ? (
          <img src={previewUrl} alt="Vista previa del certificado" className="bandeja-preview-media" />
        ) : (
          <p className="muted bandeja-preview-placeholder">La vista previa aparece acá después de elegir el archivo.</p>
        )}
      </div>
      <div className="form-field">
        <label htmlFor="respaldo-desde">Fecha de realización</label>
        <input
          id="respaldo-desde"
          type="date"
          value={vigenteDesde}
          max={hoyIso}
          disabled={busy}
          onChange={e => setVigenteDesde(e.target.value)}
          required
        />
        {erroresFecha.desde && vigenteDesde ? <p className="field-error">{erroresFecha.desde}</p> : null}
      </div>
      <div className="form-field">
        <label htmlFor="respaldo-hasta">Fecha de vencimiento</label>
        <input
          id="respaldo-hasta"
          type="date"
          value={vigenteHasta}
          disabled={busy}
          onChange={e => setVigenteHasta(e.target.value)}
          required
        />
        {erroresFecha.hasta && vigenteHasta ? <p className="field-error">{erroresFecha.hasta}</p> : null}
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="proposal-actions">
        <button
          type="button"
          className="button button-primary"
          disabled={!puedeRegistrar}
          onClick={() => void enviar()}
        >
          {busy ? 'Registrando…' : 'Registrar'}
        </button>
        <button type="button" className="button button-secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
      </div>
    </div>
  );
}
