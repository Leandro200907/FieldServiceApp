import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { ErrorState, LoadingState } from '../../ui/States';
import { GRUPOS_EDITOR, type EditorLinea, clearMatrizDraft, loadMatrizDraft, saveMatrizDraft } from './matrizDraft';
import { publicarMatrizDraft } from './matrizPublish';
import './matrices.css';

function toggleClasificacion(linea: EditorLinea): EditorLinea {
  if (linea.clasificacion === 'bloqueante_duro') {
    return { ...linea, clasificacion: 'excepcionable', bloqueante_durante_ejecucion: false };
  }
  return { ...linea, clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true };
}

export function MatrizEditorScreen() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState(loadMatrizDraft());
  const [publicando, setPublicando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addTipo, setAddTipo] = useState<string | null>(null);

  useEffect(() => {
    if (!draft) navigate('/matrices/nueva', { replace: true });
  }, [draft, navigate]);

  const definiciones = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/definiciones_requisito', {
      params: { query: { activas: true, limit: 500, offset: 0 } },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, []);

  if (!draft) return null;
  if (definiciones.loading) return <LoadingState />;

  const update = (next: typeof draft) => {
    setDraft(next);
    saveMatrizDraft(next);
  };

  const lineasPorGrupo = (grupo: string) => draft.lineas.filter(l => l.tipo_sujeto_aplicable === grupo);

  const agregar = (grupo: string, requisitoId: string) => {
    const def = definiciones.data?.items.find(d => d.requisito_definicion_id === requisitoId);
    if (!def || draft.lineas.some(l => l.requisito_definicion_id === requisitoId)) return;
    update({
      ...draft,
      lineas: [...draft.lineas, {
        requisito_definicion_id: def.requisito_definicion_id,
        nombre: def.nombre,
        tipo_sujeto_aplicable: def.tipo_sujeto_aplicable,
        categoria: def.categoria,
        incluido: true,
        clasificacion: 'bloqueante_duro',
        bloqueante_durante_ejecucion: true,
      }],
    });
    setAddTipo(null);
  };

  const publicar = async () => {
    setPublicando(true);
    setError(null);
    try {
      await publicarMatrizDraft(draft);
      clearMatrizDraft();
      navigate('/matrices');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo publicar');
    } finally {
      setPublicando(false);
    }
  };

  return (
    <section className="panel matriz-editor">
      <p className="muted matriz-leyenda-candado" title="Candado rojo cerrado: bloqueante. Candado gris abierto: excepcionable.">
        🔒 Bloqueante · 🔓 Excepcionable
      </p>
      <div className="matriz-editor-grid">
        {GRUPOS_EDITOR.map(col => (
          <div key={col.id} className="matriz-editor-col">
            <h3>{col.titulo}</h3>
            <ul className="matriz-editor-lineas">
              {lineasPorGrupo(col.id).map(linea => (
                <li key={linea.requisito_definicion_id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={linea.incluido}
                      onChange={() => update({
                        ...draft,
                        lineas: draft.lineas.map(l => l.requisito_definicion_id === linea.requisito_definicion_id ? { ...l, incluido: !l.incluido } : l),
                      })}
                    />
                    {linea.nombre}
                  </label>
                  <button
                    type="button"
                    className={`matriz-candado${linea.clasificacion === 'bloqueante_duro' ? ' bloqueante' : ' excepcionable'}`}
                    title={linea.clasificacion === 'bloqueante_duro' ? 'Bloqueante' : 'Excepcionable'}
                    onClick={() => update({
                      ...draft,
                      lineas: draft.lineas.map(l => l.requisito_definicion_id === linea.requisito_definicion_id ? toggleClasificacion(l) : l),
                    })}
                    aria-label={linea.clasificacion === 'bloqueante_duro' ? 'Bloqueante' : 'Excepcionable'}
                  >
                    {linea.clasificacion === 'bloqueante_duro' ? '🔒' : '🔓'}
                  </button>
                </li>
              ))}
            </ul>
            {addTipo === col.id ? (
              <select onChange={e => agregar(col.id, e.target.value)} defaultValue="">
                <option value="">Elegir requisito…</option>
                {(definiciones.data?.items || []).filter(d => d.tipo_sujeto_aplicable === col.id).map(d => (
                  <option key={d.requisito_definicion_id} value={d.requisito_definicion_id}>{d.nombre}</option>
                ))}
              </select>
            ) : (
              <button type="button" className="button button-secondary matriz-add-btn" onClick={() => setAddTipo(col.id)}>+ Agregar</button>
            )}
          </div>
        ))}
      </div>
      <div className="matriz-editor-footer">
        <div className="form-field">
          <label htmlFor="me-fuente">De dónde salió (fuente)</label>
          <input id="me-fuente" value={draft.fuente} onChange={e => update({ ...draft, fuente: e.target.value })} />
        </div>
        <div className="form-field">
          <label htmlFor="me-archivo">Archivo de respaldo</label>
          <input id="me-archivo" value={draft.archivoDeRespaldo} onChange={e => update({ ...draft, archivoDeRespaldo: e.target.value })} />
        </div>
        <div className="form-field">
          <label htmlFor="me-desde">Vale desde</label>
          <input id="me-desde" type="date" value={draft.vigenteDesde} onChange={e => update({ ...draft, vigenteDesde: e.target.value })} />
        </div>
        {error && <p className="field-error">{error}</p>}
        <button type="button" className="button button-primary" disabled={publicando} onClick={() => void publicar()}>
          {publicando ? 'Publicando…' : 'Publicar'}
        </button>
      </div>
    </section>
  );
}
