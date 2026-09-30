import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import './planning.css';

type Acciones = components['schemas']['AccionesPendientesResponse'];
type Accion = components['schemas']['AccionPendienteItem'];
type Catalogos = components['schemas']['CatalogosOcResponse'];

function fmtDate(value: string) {
  return new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
}

export function AccionesPendientesScreen() {
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') || 0);
  const mes = params.get('mes') || '';
  const operadoras = params.getAll('operadora_id');

  const [reloadKey, setReloadKey] = useState(0);

  const catalogosQuery = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/catalogos_oc');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Catalogos;
  }, [reloadKey]);

  const query = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/acciones_pendientes', {
      params: {
        query: {
          offset,
          limit: PAGE_SIZE,
          mes: mes || undefined,
          ...(operadoras.length ? { operadora_id: operadoras } : {}),
        },
      },
    });
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data as Acciones;
  }, [offset, mes, operadoras.join(','), reloadKey]);

  const operadoraOpts = catalogosQuery.data?.operadoras ?? [];

  const toggleOperadora = (id: string) => {
    setParams(p => {
      p.delete('offset');
      const cur = p.getAll('operadora_id');
      p.delete('operadora_id');
      if (cur.includes(id)) cur.filter(x => x !== id).forEach(x => p.append('operadora_id', x));
      else [...cur, id].forEach(x => p.append('operadora_id', x));
      return p;
    });
  };

  const items = query.data?.items ?? [];

  if (query.loading || catalogosQuery.loading) return <LoadingState />;
  if (query.error) return <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  return (
    <div className="planning-layout">
      <header className="panel">
        <h2>Acciones pendientes</h2>
        <p>Renovaciones y regularizaciones que impactan OCs activas.</p>
        <div className="form-row">
          <label>Mes<input type="month" value={mes} onChange={e => setParams(p => { p.set('mes', e.target.value); p.delete('offset'); return p; })} /></label>
        </div>
        <fieldset className="form-field">
          <legend>Operadoras</legend>
          {operadoraOpts.map(o => (
            <label key={o.operadora_id as string}>
              <input type="checkbox" checked={operadoras.includes(o.operadora_id as string)} onChange={() => toggleOperadora(o.operadora_id as string)} />
              {o.nombre as string}
            </label>
          ))}
        </fieldset>
      </header>
      <ul className="panel">
        {items.map((a: Accion, i) => (
          <li key={`${a.legajo_id}-${a.requisito}-${i}`}>
            <strong>{a.accion_sugerida}</strong> — {a.legajo_nombre} ({a.tipo_sujeto})
            {a.requisito && <> · {a.requisito}</>}
            {a.fecha_limite && <> · límite {fmtDate(a.fecha_limite)}</>}
            {a.efecto && <p>{a.efecto}</p>}
            {a.genera_alerta_cierta && <em> Genera alerta cierta</em>}
            {a.ocs_afectadas?.length > 0 && (
              <p>OCs: {a.ocs_afectadas.map(o => String((o as { clave_origen?: string }).clave_origen || '')).filter(Boolean).join(', ')}</p>
            )}
          </li>
        ))}
      </ul>
      <PaginationControls offset={offset} limit={PAGE_SIZE} total={query.data?.total ?? 0} onOffsetChange={n => setParams(p => { p.set('offset', String(n)); return p; })} />
    </div>
  );
}
