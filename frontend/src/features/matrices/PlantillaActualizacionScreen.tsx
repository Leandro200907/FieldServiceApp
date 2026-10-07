import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { ErrorState, LoadingState } from '../../ui/States';
import type { CambioPlantilla } from './matrizDraft';
import { ejecutarTraerCambiosPlantilla } from './plantillaTraer';

const iconoCambio: Record<CambioPlantilla['tipo'], string> = {
  agregado: '➕',
  quitado: '➖',
  pasa_a_bloquear: '🔒',
  deja_de_bloquear: '🔓',
};

export function PlantillaActualizacionScreen() {
  const { pathname } = useLocation();
  const match = pathname.match(/\/matrices\/plantilla\/([^/]+)\/([^/]+)/);
  const matrizGlobalId = match?.[1] || '';
  const copiaId = match?.[2] || '';
  const navigate = useNavigate();
  const [seleccion, setSeleccion] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const plantillas = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/plantillas_globales');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, []);

  const matricesMeta = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/matrices', { params: { query: { limit: 1, offset: 0 } } });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, []);

  const copia = useMemo(() => {
    const m = plantillas.data?.matrices.find(x => x.matriz_global_id === matrizGlobalId);
    return m?.copias_locales.find(c => c.matriz_version_id === copiaId) ?? null;
  }, [plantillas.data, matrizGlobalId, copiaId]);

  const cambios: CambioPlantilla[] = copia?.cambios || [];
  const key = (c: CambioPlantilla, i: number) => `${c.tipo}-${c.definicion_global_id || c.requisito_definicion_id || i}`;

  const todos = useMemo(() => {
    const m: Record<string, boolean> = {};
    cambios.forEach((c, i) => { m[key(c, i)] = seleccion[key(c, i)] ?? true; });
    return m;
  }, [cambios, seleccion]);

  const nTraer = Object.values(todos).filter(Boolean).length;
  const hoy = matricesMeta.data?.hoy;

  const traer = async () => {
    if (!copia || !hoy) {
      setError('No se pudo obtener la fecha de hoy del servidor');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const elegidos = cambios.filter((c, i) => todos[key(c, i)]);
      await ejecutarTraerCambiosPlantilla(
        copia,
        matrizGlobalId,
        cambios,
        elegidos,
        plantillas.data?.definiciones || [],
        hoy.slice(0, 10),
      );
      navigate('/matrices');
    } catch (e) {
      setError(e instanceof ApiFailure ? e.message : e instanceof Error ? e.message : 'Error al traer cambios');
    } finally {
      setBusy(false);
    }
  };

  if (plantillas.loading || matricesMeta.loading) return <LoadingState />;
  if (plantillas.error) return <ErrorState message={plantillas.error.message} />;

  return (
    <section className="panel">
      <h2>Cambios de plantilla</h2>
      <ul className="matriz-cambios-list">
        {cambios.map((c, i) => {
          const k = key(c, i);
          return (
            <li key={k}>
              <span aria-hidden>{iconoCambio[c.tipo]}</span>
              <span>{c.grupo} · {c.nombre}</span>
              <span className="muted">v{c.version_origen}→v{c.version_destino}</span>
              <label>
                <input type="checkbox" checked={todos[k]} onChange={() => setSeleccion(s => ({ ...s, [k]: !(s[k] ?? true) }))} />
                Traer
              </label>
            </li>
          );
        })}
      </ul>
      {error && <p className="field-error">{error}</p>}
      <div className="matriz-actions">
        <button type="button" className="button button-secondary" onClick={() => navigate('/matrices')}>Ahora no</button>
        <button type="button" className="button button-primary" disabled={busy || nTraer === 0} onClick={() => void traer()}>
          Traer {nTraer} cambios
        </button>
      </div>
    </section>
  );
}
