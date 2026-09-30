import { useMemo, useState } from 'react';
import { ApiFailure, parseApiError, session } from '../../api';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import './planning.css';

type Catalogos = components['schemas']['CatalogosOcResponse'];

export function CatalogosOcScreen() {
  const [reloadKey, setReloadKey] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const [nuevaOperadora, setNuevaOperadora] = useState('');
  const [nuevaLocacion, setNuevaLocacion] = useState('');
  const [locOperadora, setLocOperadora] = useState('');
  const [nuevoTipo, setNuevoTipo] = useState('');

  const query = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/catalogos_oc');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Catalogos;
  }, [reloadKey]);

  const operadoras = query.data?.operadoras ?? [];
  const locaciones = query.data?.locaciones ?? [];
  const tipos = query.data?.tipos_servicio ?? [];

  const locPorOperadora = useMemo(() => {
    const map = new Map<string, typeof locaciones>();
    for (const l of locaciones) {
      const op = l.operadora_id as string;
      if (!map.has(op)) map.set(op, []);
      map.get(op)!.push(l);
    }
    return map;
  }, [locaciones]);

  const nombresOperadora = useMemo(() => new Set(operadoras.map(o => (o.nombre as string).trim().toLowerCase())), [operadoras]);
  const nombresTipo = useMemo(() => new Set(tipos.map(t => (t.nombre as string).trim().toLowerCase())), [tipos]);

  const post = async (path: '/v1/comandos/alta_operadora_oc' | '/v1/comandos/alta_locacion_oc' | '/v1/comandos/alta_tipo_servicio_oc', body: Record<string, unknown>) => {
    setMsg(null);
    const res = await session.client.POST(path, { body } as never);
    if (res.error || !res.response.ok) {
      const err = parseApiError(res.error, res.response, res.response.headers.get('X-Request-ID') || crypto.randomUUID());
      setMsg(err.message);
      return;
    }
    setMsg('Guardado correctamente');
    setReloadKey(k => k + 1);
  };

  if (query.loading) return <LoadingState />;
  if (query.error) return <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  return (
    <div className="planning-layout">
      <header className="panel">
        <h2>Catálogos de OC</h2>
        <p>Operadoras, locaciones y tipos de servicio usados en la planilla de OC.</p>
        {msg && <p role="status">{msg}</p>}
      </header>

      <section className="panel">
        <h3>Operadoras</h3>
        <ul>{operadoras.map(o => <li key={o.operadora_id as string}>{o.nombre as string}</li>)}</ul>
        <form
          className="form-row"
          onSubmit={e => {
            e.preventDefault();
            const nombre = nuevaOperadora.trim();
            if (!nombre) { setMsg('El nombre de operadora no puede estar vacío'); return; }
            if (nombresOperadora.has(nombre.toLowerCase())) { setMsg('Operadora duplicada'); return; }
            void post('/v1/comandos/alta_operadora_oc', { nombre });
            setNuevaOperadora('');
          }}
        >
          <label>Nueva operadora<input value={nuevaOperadora} onChange={e => setNuevaOperadora(e.target.value)} /></label>
          <button type="submit" className="button button-primary">Agregar</button>
        </form>
      </section>

      <section className="panel">
        <h3>Locaciones</h3>
        {operadoras.map(o => (
          <div key={o.operadora_id as string}>
            <h4>{o.nombre as string}</h4>
            <ul>{(locPorOperadora.get(o.operadora_id as string) || []).map(l => <li key={l.locacion_id as string}>{l.nombre as string}</li>)}</ul>
          </div>
        ))}
        <form
          className="form-row"
          onSubmit={e => {
            e.preventDefault();
            const nombre = nuevaLocacion.trim();
            if (!locOperadora) { setMsg('Elegí una operadora'); return; }
            if (!nombre) { setMsg('El nombre de locación no puede estar vacío'); return; }
            const dup = (locPorOperadora.get(locOperadora) || []).some(l => (l.nombre as string).trim().toLowerCase() === nombre.toLowerCase());
            if (dup) { setMsg('Locación duplicada en esta operadora'); return; }
            void post('/v1/comandos/alta_locacion_oc', { operadora_id: locOperadora, nombre });
            setNuevaLocacion('');
          }}
        >
          <label>Operadora
            <select value={locOperadora} onChange={e => setLocOperadora(e.target.value)}>
              <option value="">—</option>
              {operadoras.map(o => <option key={o.operadora_id as string} value={o.operadora_id as string}>{o.nombre as string}</option>)}
            </select>
          </label>
          <label>Nueva locación<input value={nuevaLocacion} onChange={e => setNuevaLocacion(e.target.value)} /></label>
          <button type="submit" className="button button-primary">Agregar</button>
        </form>
      </section>

      <section className="panel">
        <h3>Tipos de servicio</h3>
        <ul>{tipos.map(t => <li key={t.tipo_servicio_id as string}>{t.nombre as string}</li>)}</ul>
        <form
          className="form-row"
          onSubmit={e => {
            e.preventDefault();
            const nombre = nuevoTipo.trim();
            if (!nombre) { setMsg('El nombre no puede estar vacío'); return; }
            if (nombresTipo.has(nombre.toLowerCase())) { setMsg('Tipo de servicio duplicado'); return; }
            void post('/v1/comandos/alta_tipo_servicio_oc', { nombre });
            setNuevoTipo('');
          }}
        >
          <label>Nuevo tipo<input value={nuevoTipo} onChange={e => setNuevoTipo(e.target.value)} /></label>
          <button type="submit" className="button button-primary">Agregar</button>
        </form>
      </section>
    </div>
  );
}
