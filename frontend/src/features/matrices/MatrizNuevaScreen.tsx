import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { ErrorState, LoadingState } from '../../ui/States';
import type { ModoArranque, MatrizDraft } from './matrizDraft';
import { lineaFromVigente, saveMatrizDraft } from './matrizDraft';
import type { components } from '../../api/generated/modulo1';

type Plantillas = components['schemas']['PlantillasGlobalesResponse'];

function findPlantilla(plantillas: Plantillas | null, operadoraNombre: string, servicioNombre: string) {
  if (!plantillas) return null;
  const on = operadoraNombre.toLowerCase();
  const sn = servicioNombre.toLowerCase();
  return plantillas.matrices.find(m => m.operadora.toLowerCase() === on && m.tipo_servicio.toLowerCase() === sn)
    ?? plantillas.matrices.find(m => m.operadora.toLowerCase() === on)
    ?? null;
}

export function MatrizNuevaScreen() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [clienteId, setClienteId] = useState(params.get('cliente_id') || '');
  const [locacionId, setLocacionId] = useState(params.get('locacion_id') || '');
  const [tipoServicioId, setTipoServicioId] = useState(params.get('tipo_servicio_id') || '');
  const [modo, setModo] = useState<ModoArranque>('plantilla');
  const [copiarId, setCopiarId] = useState('');
  const [error, setError] = useState<string | null>(null);

  const catalogos = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/catalogos_oc');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, []);

  const plantillas = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/plantillas_globales');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, []);

  const matrices = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/matrices', { params: { query: { solo_vigentes: true, limit: 200, offset: 0 } } });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, []);

  type Op = { operadora_id: string; nombre: string };
  type Loc = { locacion_id: string; operadora_id: string; nombre: string };
  type Ts = { tipo_servicio_id: string; nombre: string };
  const operadoras = (catalogos.data?.operadoras || []) as Op[];
  const operadora = operadoras.find(o => o.operadora_id === clienteId);
  const locaciones = useMemo(
    () => ((catalogos.data?.locaciones || []) as Loc[]).filter(l => l.operadora_id === clienteId),
    [catalogos.data, clienteId],
  );
  const servicios = (catalogos.data?.tipos_servicio || []) as Ts[];
  const plantilla = findPlantilla(plantillas.data ?? null, operadora?.nombre || '', servicios.find(s => s.tipo_servicio_id === tipoServicioId)?.nombre || '');
  const hoy = matrices.data?.hoy || '2026-09-18';

  const seguir = async () => {
    setError(null);
    if (!clienteId || !locacionId || !tipoServicioId) {
      setError('Elegí operadora, locación y servicio');
      return;
    }
    const draft: MatrizDraft = {
      clienteId, locacionId, tipoServicioId, modo,
      matrizGlobalId: modo === 'plantilla' ? plantilla?.matriz_global_id : undefined,
      vigenteDesde: hoy.slice(0, 10),
      fuente: modo === 'plantilla' ? `Plantilla ${plantilla?.operadora} · ${plantilla?.tipo_servicio}` : modo === 'copiar' ? 'Copia de matriz existente' : 'Matriz manual',
      archivoDeRespaldo: '',
      lineas: [],
    };
    try {
      if (modo === 'copiar') {
        const item = matrices.data?.items.find(m => m.matriz_version_id === copiarId);
        if (!item) throw new Error('Elegí una matriz para copiar');
        draft.copiarDesde = { clienteId: item.cliente_id, locacionId: item.locacion_id, tipoServicioId: item.tipo_servicio_id };
        const mv = await session.client.GET('/v1/consultas/matriz_vigente', {
          params: { query: { cliente_id: item.cliente_id, locacion_id: item.locacion_id, tipo_servicio_id: item.tipo_servicio_id, fecha: hoy.slice(0, 10) } },
        });
        if (mv.error || !mv.response.ok) throw new Error('No se pudo leer la matriz origen');
        draft.lineas = (mv.data?.lineas || []).map(lineaFromVigente);
      } else if (modo === 'cero') {
        draft.lineas = [];
      } else {
        draft.lineas = [];
      }
      saveMatrizDraft(draft);
      navigate('/matrices/editor');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al continuar');
    }
  };

  if (catalogos.loading || plantillas.loading || matrices.loading) return <LoadingState />;
  if (catalogos.error) return <ErrorState message={catalogos.error.message} />;

  const tituloPlantilla = plantilla ? `Plantilla ${plantilla.operadora} · ${plantilla.tipo_servicio}` : null;

  return (
    <section className="panel matriz-wizard">
      <h2>Nueva matriz</h2>
      <div className="form-field">
        <label htmlFor="mn-operadora">Operadora</label>
        <select id="mn-operadora" value={clienteId} onChange={e => { setClienteId(e.target.value); setLocacionId(''); }}>
          <option value="">Elegir…</option>
          {operadoras.map(o => <option key={o.operadora_id} value={o.operadora_id}>{o.nombre}</option>)}
        </select>
      </div>
      <div className="form-field">
        <label htmlFor="mn-locacion">Locación</label>
        <select id="mn-locacion" value={locacionId} onChange={e => setLocacionId(e.target.value)} disabled={!clienteId}>
          <option value="">Elegir…</option>
          {locaciones.map(l => <option key={l.locacion_id} value={l.locacion_id}>{l.nombre}</option>)}
        </select>
      </div>
      <div className="form-field">
        <label htmlFor="mn-servicio">Servicio</label>
        <select id="mn-servicio" value={tipoServicioId} onChange={e => setTipoServicioId(e.target.value)}>
          <option value="">Elegir…</option>
          {servicios.map(s => <option key={s.tipo_servicio_id} value={s.tipo_servicio_id}>{s.nombre}</option>)}
        </select>
      </div>
      <p className="muted">Cómo arrancar</p>
      <div className="matriz-arranque-cards">
        {tituloPlantilla && (
          <button type="button" className={`matriz-arranque-card${modo === 'plantilla' ? ' selected' : ''}`} onClick={() => setModo('plantilla')}>
            <span className="matriz-arranque-icon" aria-hidden>📋</span>
            <span>{tituloPlantilla}</span>
          </button>
        )}
        <button type="button" className={`matriz-arranque-card${modo === 'copiar' ? ' selected' : ''}`} onClick={() => setModo('copiar')}>
          <span className="matriz-arranque-icon" aria-hidden>📑</span>
          <span>Copiar una matriz mía</span>
        </button>
        <button type="button" className={`matriz-arranque-card${modo === 'cero' ? ' selected' : ''}`} onClick={() => setModo('cero')}>
          <span className="matriz-arranque-icon" aria-hidden>✨</span>
          <span>Desde cero</span>
        </button>
      </div>
      {modo === 'copiar' && (
        <div className="form-field">
          <label htmlFor="mn-copiar">Matriz vigente</label>
          <select id="mn-copiar" value={copiarId} onChange={e => setCopiarId(e.target.value)}>
            <option value="">Elegir…</option>
            {(matrices.data?.items || []).map(m => (
              <option key={m.matriz_version_id} value={m.matriz_version_id}>
                {[m.operadora_nombre, m.locacion_nombre, m.tipo_servicio_nombre].filter(Boolean).join(' · ')} (v{m.version})
              </option>
            ))}
          </select>
        </div>
      )}
      {error && <p className="field-error">{error}</p>}
      <div className="matriz-actions">
        <button type="button" className="button button-secondary" onClick={() => navigate('/matrices')}>Cancelar</button>
        <button type="button" className="button button-primary" onClick={() => void seguir()}>Seguir</button>
      </div>
    </section>
  );
}
