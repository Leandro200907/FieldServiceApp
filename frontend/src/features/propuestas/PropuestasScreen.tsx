import { useMemo, useRef, useState } from 'react';
import { ApiFailure } from '../../api';
import { Badge, ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { propuestasAccess } from './access';
import { subtituloLegajoPersona, tituloLegajoPersona } from '../legajos/legajoDisplay';
import { session } from '../../api';
import { formatFecha, formatFechaHora } from '../../ui/fechas';
import type { ItemBandejaRevision, PestanaBandeja, PropuestasAccess } from './contracts';
import { OcsAfectadasLine } from '../../ui/OcsAfectadasLine';
import '../documentation-planning/planning.css';
import './propuestas.css';

function abrirUrlDescarga(url: string) {
  const absolute = url.startsWith('http') ? url : `${window.location.origin}${url.startsWith('/') ? '' : '/'}${url}`;
  window.open(absolute, '_blank', 'noopener,noreferrer');
}

function DetalleBandeja({
  item,
  access,
  readOnly,
  archivoAbierto,
  onArchivoAbierto,
  onChanged,
  onSiguiente,
  haySiguiente,
}: {
  item: ItemBandejaRevision;
  access: PropuestasAccess;
  readOnly: boolean;
  archivoAbierto: boolean;
  onArchivoAbierto: () => void;
  onChanged: () => void;
  onSiguiente: () => void;
  haySiguiente: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const confirmarKey = useRef<string | null>(null);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const sujeto = {
    tipo_sujeto: item.tipo_sujeto ?? 'persona',
    nombre_apellido: item.nombre_apellido ?? null,
    identificador_natural: item.identificador_natural ?? item.sujeto_id,
  };
  const esPropuesta = item.tipo_item === 'propuesta';
  const sinArchivoValido = item.archivo_validacion !== 'valido' && item.tipo_item === 'propuesta';

  async function abrirArchivo() {
    setBusy(true);
    setError(null);
    try {
      const r = await access.abrirArchivo(item.documento_id);
      setPreviewUrl(r.url);
      onArchivoAbierto();
      abrirUrlDescarga(r.url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'No se pudo abrir el archivo.');
    } finally {
      setBusy(false);
    }
  }

  async function confirmar() {
    setBusy(true);
    setError(null);
    confirmarKey.current ??= crypto.randomUUID();
    try {
      await access.confirmarDocumento(item.documento_id, confirmarKey.current);
      confirmarKey.current = null;
      onChanged();
      if (haySiguiente) onSiguiente();
    } catch (caught) {
      if (caught instanceof ApiFailure && caught.detail.status > 0) confirmarKey.current = null;
      setError(caught instanceof Error ? caught.message : 'Error al confirmar');
    } finally {
      setBusy(false);
    }
  }

  async function rechazar() {
    const motivoNormalizado = motivo.trim();
    if (!motivoNormalizado) return;
    setBusy(true);
    setError(null);
    try {
      await access.rechazarPropuesta(item.documento_id, motivoNormalizado, crypto.randomUUID());
      setRejecting(false);
      setMotivo('');
      onChanged();
      if (haySiguiente) onSiguiente();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Error al rechazar');
    } finally {
      setBusy(false);
    }
  }

  const puedeConfirmarPropuesta = esPropuesta && archivoAbierto && !sinArchivoValido;

  return (
    <section className="bandeja-detalle panel">
      <h2>{tituloLegajoPersona(sujeto)}</h2>
      {subtituloLegajoPersona(sujeto) && <p className="muted">{subtituloLegajoPersona(sujeto)}</p>}
      <p><strong>{item.requisito}</strong> · <Badge tone="accent">{item.tipo_item === 'propuesta' ? 'Propuesta' : 'Archivo'}</Badge></p>
      <p className="muted">{item.estado_presentacion_explicacion}</p>

      <div className="bandeja-comparacion">
        <div>
          <h4>Vigente</h4>
          {item.vigente_comparacion ? (
            <p>{formatFecha(item.vigente_comparacion.vigente_desde ?? '', tz)} — {formatFecha(item.vigente_comparacion.vigente_hasta ?? '', tz)}</p>
          ) : <p className="muted">Sin versión vigente previa</p>}
        </div>
        {esPropuesta && item.propuesta && (
          <div>
            <h4>Propuesta</h4>
            <p>{formatFecha(item.propuesta.vigente_desde ?? '', tz)} — {formatFecha(item.propuesta.vigente_hasta ?? '', tz)}</p>
            {item.propuesta.cargado_por?.nombre && <small className="muted">Cargado por {item.propuesta.cargado_por.nombre}</small>}
          </div>
        )}
      </div>

      {(item.ocs_afectadas?.length ?? 0) > 0 && (
        <p><OcsAfectadasLine ocs={item.ocs_afectadas as never} hoyIso={new Date().toISOString().slice(0, 10)} timeZone={tz} /></p>
      )}

      <div className="bandeja-archivo">
        <button type="button" className="button button-secondary" disabled={busy || readOnly || sinArchivoValido} onClick={() => void abrirArchivo()}>
          Ver archivo
        </button>
        {previewUrl && <p className="muted">Archivo abierto en una pestaña nueva.</p>}
        {esPropuesta && !archivoAbierto && !sinArchivoValido && <p className="muted" role="note">Abrí el archivo antes de confirmar (E-78).</p>}
        {item.archivo_validacion_motivo && <p className="field-error">{item.archivo_validacion_motivo}</p>}
      </div>

      {error && <p className="field-error" role="alert">{error}</p>}

      {esPropuesta && (
        <div className="proposal-actions">
          {!rejecting ? (
            <>
              <button type="button" className="button button-primary" disabled={busy || readOnly || !puedeConfirmarPropuesta} onClick={() => void confirmar()}>
                Confirmar y seguir
              </button>
              <button type="button" className="button button-secondary" disabled={busy || readOnly} onClick={() => setRejecting(true)}>Rechazar</button>
            </>
          ) : (
            <div className="proposal-reject">
              <label htmlFor={`motivo-${item.documento_id}`}>Motivo del rechazo (obligatorio)</label>
              <input id={`motivo-${item.documento_id}`} value={motivo} onChange={e => setMotivo(e.target.value)} disabled={busy || readOnly} required />
              <button type="button" className="button button-primary" disabled={busy || readOnly || !motivo.trim()} onClick={() => void rechazar()}>Confirmar rechazo</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => setRejecting(false)}>Cancelar</button>
            </div>
          )}
        </div>
      )}
      <small className="muted">Ingresó {formatFechaHora(item.creado_en ?? '', tz)}</small>
    </section>
  );
}

export function PropuestasScreen({ accessOverride, readOnly = false }: { accessOverride?: PropuestasAccess; readOnly?: boolean } = {}) {
  const access = accessOverride ?? propuestasAccess();
  const [pestana, setPestana] = useState<PestanaBandeja>('todos');
  const [offset, setOffset] = useState(0);
  const [refreshToken, setRefreshToken] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [archivosAbiertos, setArchivosAbiertos] = useState<Record<string, boolean>>({});

  const bandeja = usePrototypeRead(
    () => access.readBandejaRevision({ offset, limit: PAGE_SIZE, pestana }),
    [access, offset, pestana, refreshToken],
  );

  const items = bandeja.data?.items ?? [];
  const selected = useMemo(() => items.find(i => i.documento_id === selectedId) ?? items[0] ?? null, [items, selectedId]);
  const selectedIndex = selected ? items.findIndex(i => i.documento_id === selected.documento_id) : -1;

  function onChanged() {
    setRefreshToken(t => t + 1);
  }

  function onSiguiente() {
    if (selectedIndex >= 0 && selectedIndex < items.length - 1) {
      setSelectedId(items[selectedIndex + 1].documento_id);
    } else {
      setSelectedId(null);
    }
  }

  return (
    <>
      <header className="bandeja-header">
        <h1 className="page-title">Bandeja de revisión</h1>
        <div className="bandeja-tabs" role="tablist">
          {(['todos', 'propuestas', 'archivos'] as const).map(p => (
            <button
              key={p}
              type="button"
              role="tab"
              aria-selected={pestana === p}
              className={pestana === p ? 'tab active' : 'tab'}
              onClick={() => { setPestana(p); setOffset(0); setSelectedId(null); }}
            >
              {p === 'todos' ? 'Todos' : p === 'propuestas' ? 'Propuestas' : 'Archivos'}
              {bandeja.data?.conteos && <span className="tab-count"> ({bandeja.data.conteos[p]})</span>}
            </button>
          ))}
        </div>
      </header>
      {readOnly && <div className="availability-warning" role="note"><strong>Vista de diseño no interactiva</strong></div>}
      {bandeja.loading ? <LoadingState /> : bandeja.error ? (
        <ErrorState message={bandeja.error.message} requestId={bandeja.error instanceof ApiFailure && bandeja.error.detail.referenceSource === 'server' ? bandeja.error.detail.requestId : undefined} />
      ) : (
        <div className="bandeja-layout">
          <ul className="bandeja-lista">
            {items.map(item => (
              <li key={item.documento_id}>
                <button
                  type="button"
                  className={selected?.documento_id === item.documento_id ? 'bandeja-item active' : 'bandeja-item'}
                  onClick={() => setSelectedId(item.documento_id)}
                >
                  <strong>{item.nombre_apellido || item.identificador_natural}</strong>
                  <span>{item.requisito}</span>
                  <small>{item.tipo_item}</small>
                </button>
              </li>
            ))}
            {items.length === 0 && <p className="empty-inline">Sin ítems en esta pestaña.</p>}
          </ul>
          {selected ? (
            <DetalleBandeja
              item={selected}
              access={access}
              readOnly={readOnly}
              archivoAbierto={Boolean(archivosAbiertos[selected.documento_id])}
              onArchivoAbierto={() => setArchivosAbiertos(prev => ({ ...prev, [selected.documento_id]: true }))}
              onChanged={onChanged}
              onSiguiente={onSiguiente}
              haySiguiente={selectedIndex >= 0 && selectedIndex < items.length - 1}
            />
          ) : (
            <p className="empty-inline bandeja-detalle panel">Elegí un ítem de la lista.</p>
          )}
        </div>
      )}
    </>
  );
}
