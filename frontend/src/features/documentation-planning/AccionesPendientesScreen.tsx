import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import type { components } from '../../api/generated/modulo1';
import { ErrorState, LoadingState } from '../../ui/States';
import { textoQueHacerAccion } from './copy';
import { formatFecha, todayIso } from './dates';
import { OcsAfectadasLine } from '../../ui/OcsAfectadasLine';
import type { OcAfectadaRef } from '../../ui/ocsAfectadasPresentacion';
import { lineaPersonaConDni } from '../legajos/legajoDisplay';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { esCargaInicial, usePrototypeRead } from '../../hooks/usePrototypeRead';
import './planning.css';

type Acciones = components['schemas']['AccionesPendientesResponse'];
type Accion = components['schemas']['AccionPendienteItem'];
type Catalogos = components['schemas']['CatalogosOcResponse'];

export function AccionesPendientesScreen() {
  const [params, setParams] = useSearchParams();
  const offset = Number(params.get('offset') || 0);
  const mes = params.get('mes') || '';
  const operadoras = params.getAll('operadora_id');
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const hoy = todayIso();

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

  const items = useMemo(() => {
    const list = [...(query.data?.items ?? [])];
    list.sort((a, b) => {
      const aBloquea = a.fecha_limite < hoy ? 0 : 1;
      const bBloquea = b.fecha_limite < hoy ? 0 : 1;
      if (aBloquea !== bBloquea) return aBloquea - bBloquea;
      return a.fecha_limite.localeCompare(b.fecha_limite);
    });
    return list;
  }, [query.data?.items, hoy]);

  const cargaInicial = esCargaInicial(query) || esCargaInicial(catalogosQuery);
  if (cargaInicial) return <LoadingState />;
  if (query.error && !query.data) return <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />;

  return (
    <div className="planning-layout">
      <header className="panel">
        <h2>Acciones pendientes</h2>
        <p>Renovaciones y regularizaciones que impactan OCs activas.</p>
        <div className="form-field">
          <label htmlFor="acciones-mes">Mes</label>
          <input id="acciones-mes" type="month" value={mes} onChange={e => setParams(p => { p.set('mes', e.target.value); p.delete('offset'); return p; })} />
        </div>
        <p className="eyebrow">Operadora</p>
        <div className="espejo-filter-chips">
          {operadoraOpts.map(o => (
            <label key={o.operadora_id as string} className="checkbox-inline">
              <input type="checkbox" checked={operadoras.includes(o.operadora_id as string)} onChange={() => toggleOperadora(o.operadora_id as string)} />
              {o.nombre as string}
            </label>
          ))}
        </div>
      </header>
      {query.loading ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState message={query.error.message} onRetry={() => setReloadKey(k => k + 1)} />
      ) : (
        <>
          <div className="projection-table-wrap">
            <table className="projection-table">
              <thead>
                <tr>
                  <th>Quién</th>
                  <th>Qué hacer</th>
                  <th>Requisito</th>
                  <th>Desde cuándo bloquea</th>
                  <th>OC afectadas</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((a: Accion, i) => (
                  <tr key={`${a.legajo_id}-${a.requisito}-${i}`}>
                    <td>{lineaPersonaConDni({ tipo_sujeto: a.tipo_sujeto, nombre_apellido: a.nombre_apellido ?? a.legajo_nombre, identificador_natural: a.identificador_natural ?? a.legajo_id, sujeto_id: a.legajo_id })}</td>
                    <td>{textoQueHacerAccion(a.accion_sugerida, a.fecha_limite, hoy, tz)}</td>
                    <td>{a.requisito || '—'}</td>
                    <td>{formatFecha(a.fecha_limite, tz)}</td>
                    <td>
                      {a.ocs_afectadas?.length ? (
                        <OcsAfectadasLine ocs={a.ocs_afectadas as OcAfectadaRef[]} hoyIso={hoy} timeZone={tz} />
                      ) : '—'}
                    </td>
                    <td><Link className="button button-secondary" to={`/legajos/${a.legajo_id}`}>Ir al legajo</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {items.length === 0 && <p className="empty-inline">Sin acciones pendientes para estos filtros.</p>}
          <PaginationControls offset={offset} limit={PAGE_SIZE} total={query.data?.total ?? 0} onOffsetChange={n => setParams(p => { p.set('offset', String(n)); return p; })} />
        </>
      )}
    </div>
  );
}
