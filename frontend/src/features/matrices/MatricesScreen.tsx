import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiFailure, parseApiError, session } from '../../api';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { matricesAccess } from './access';
import type { MatrizItem } from './contracts';
import { ListDetailLayout } from '../../ui/ListDetailLayout';
import { StatusDot } from '../../ui/StatusDot';
import { formatFecha } from '../documentation-planning/dates';
import { etiquetaCategoria } from '../../ui/categoriaLabels';
import { MatrizNuevaScreen } from './MatrizNuevaScreen';
import { MatrizEditorScreen } from './MatrizEditorScreen';
import { PlantillaActualizacionScreen } from './PlantillaActualizacionScreen';
import '../documentation-planning/planning.css';
import './matrices.css';

const clasificacionLabels: Record<string, string> = { bloqueante_duro: 'Bloqueante', excepcionable: 'Excepcionable' };

function tituloMatriz(item: MatrizItem): string {
  const ctx = [item.operadora_nombre, item.locacion_nombre, item.tipo_servicio_nombre].filter(Boolean).join(' · ');
  return ctx || `${item.cliente_id}`;
}

function etiquetaVersion(item: MatrizItem, fmt: (iso: string) => string): string {
  if (item.vigente_hoy) return `v${item.version} vigente`;
  return `Vigente del ${fmt(item.vigente_desde)} al ${fmt(item.vigente_hasta!)}`;
}

function MatricesListado({ detailId }: { detailId?: string }) {
  const navigate = useNavigate();
  const [clienteId, setClienteId] = useState('');
  const [soloVigentes, setSoloVigentes] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<MatrizItem | null>(null);
  const roles = session.getSnapshot().identity?.roles ?? [];
  const puedeEditar = roles.includes('responsable_legajos') || roles.includes('configuracion');
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const fmt = (iso: string) => formatFecha(iso, tz);

  const catalogos = usePrototypeRead(async () => {
    const { data, error, response } = await session.client.GET('/v1/consultas/catalogos_oc');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, []);

  const plantillas = usePrototypeRead(async () => {
    if (!puedeEditar) return null;
    const { data, error, response } = await session.client.GET('/v1/consultas/plantillas_globales');
    if (error || !response.ok) throw new ApiFailure(parseApiError(error, response, response.headers.get('X-Request-ID') || crypto.randomUUID()));
    return data;
  }, [puedeEditar]);

  const actualizaciones = useMemo(() => {
    if (!plantillas.data) return [];
    return plantillas.data.matrices.flatMap(m =>
      m.copias_locales
        .filter(c => c.estado === 'actualizacion_disponible' && (c.cambios?.length ?? 0) > 0)
        .map(c => ({ matriz: m, copia: c })),
    );
  }, [plantillas.data]);

  const versiones = usePrototypeRead(() => matricesAccess().readMatrices({ clienteId: clienteId || undefined, soloVigentes, offset, limit: PAGE_SIZE }), [clienteId, soloVigentes, offset]);
  const detalle = usePrototypeRead(
    () => selected ? matricesAccess().readMatrizVigente({ clienteId: selected.cliente_id, locacionId: selected.locacion_id, tipoServicioId: selected.tipo_servicio_id, fecha: selected.vigente_desde }) : Promise.resolve(null),
    [selected],
  );

  useEffect(() => {
    if (!detailId || !versiones.data) return;
    const item = versiones.data.items.find(i => i.matriz_version_id === detailId);
    if (item) setSelected(item);
  }, [detailId, versiones.data]);

  const abrir = (item: MatrizItem) => {
    setSelected(item);
    navigate(`/matrices/${item.matriz_version_id}`);
  };
  const cerrar = () => { setSelected(null); navigate('/matrices'); };

  const operadoras = catalogos.data?.operadoras ?? [];

  const list = (
    <>
      {puedeEditar && (
        <div className="matrices-toolbar">
          <Link className="button button-primary" to="/matrices/nueva">Nueva matriz</Link>
        </div>
      )}
      {actualizaciones.length > 0 && (
        <div className="matriz-aviso-plantilla" role="status">
          <span aria-hidden>📢</span>
          <span>Hay actualizaciones de plantilla disponibles.</span>
          <Link className="button button-secondary" to={`/matrices/plantilla/${actualizaciones[0].matriz.matriz_global_id}/${actualizaciones[0].copia.matriz_version_id}`}>
            Ver cambios
          </Link>
        </div>
      )}
      <div className="form-field">
        <label htmlFor="matriz-operadora">Operadora</label>
        <select id="matriz-operadora" value={clienteId} onChange={event => { setClienteId(event.target.value); setOffset(0); }}>
          <option value="">Todas</option>
          {operadoras.map(o => <option key={o.operadora_id as string} value={o.operadora_id as string}>{o.nombre as string}</option>)}
        </select>
      </div>
      <div className="form-field checkbox-inline">
        <label htmlFor="matriz-vigentes">
          <input id="matriz-vigentes" type="checkbox" checked={soloVigentes} onChange={event => { setSoloVigentes(event.target.checked); setOffset(0); }} />
          Solo vigentes hoy
        </label>
      </div>
      {versiones.loading ? <LoadingState /> : versiones.error ? <ErrorState message={versiones.error.message} requestId={versiones.error instanceof ApiFailure && versiones.error.detail.referenceSource === 'server' ? versiones.error.detail.requestId : undefined} /> : (
        <>
          {versiones.data?.items.map(item => (
            <button key={item.matriz_version_id} type="button" className={`list-item-button${selected?.matriz_version_id === item.matriz_version_id ? ' selected' : ''}`} onClick={() => abrir(item)}>
              <span>
                <span className="list-item-primary">{tituloMatriz(item)}</span>
                <span className="list-item-secondary">Versión {item.version} — vigente desde {fmt(item.vigente_desde)}</span>
              </span>
              <StatusDot variant={item.vigente_hoy ? 'vigente' : 'neutral'}>{etiquetaVersion(item, fmt)}</StatusDot>
            </button>
          ))}
          {versiones.data?.items.length === 0 && <p className="empty-inline">Sin versiones que coincidan con el filtro.</p>}
          {versiones.data && <PaginationControls offset={versiones.data.offset} limit={versiones.data.limit} total={versiones.data.total} onOffsetChange={setOffset} />}
        </>
      )}
    </>
  );

  const detail = selected && (detalle.loading ? <LoadingState /> : detalle.error ? (
    <ErrorState message={detalle.error.message} requestId={detalle.error instanceof ApiFailure && detalle.error.detail.referenceSource === 'server' ? detalle.error.detail.requestId : undefined} />
  ) : detalle.data && (
    <>
      <p className="ficha-breadcrumb">Matrices / Detalle</p>
      <h2 className="ficha-titulo">{tituloMatriz(selected)}</h2>
      <p className="ficha-subtitulo">Versión {detalle.data.version} — vigente desde {fmt(selected.vigente_desde)}{selected.vigente_hasta ? ` — hasta ${fmt(selected.vigente_hasta)}` : ''}</p>
      <p className="muted">Consultada al {fmt(detalle.data.fecha_consultada.slice(0, 10))}</p>
      <ul className="evidence-list">
        {detalle.data.lineas.map(linea => (
          <li key={linea.requisito_definicion_id} className="evidence-row">
            <span className="evidence-name">{linea.requisito || 'Requisito sin nombre'}</span>
            <StatusDot variant={linea.clasificacion === 'bloqueante_duro' ? 'por_vencer' : 'neutral'}>{clasificacionLabels[linea.clasificacion] || linea.clasificacion}</StatusDot>
            <small>{linea.tipo_sujeto_aplicable || 'Cualquier sujeto'} · {etiquetaCategoria(linea.categoria)}</small>
          </li>
        ))}
      </ul>
      {detalle.data.lineas.length === 0 && <p className="empty-inline">Esta versión no tiene líneas.</p>}
    </>
  ));

  return <ListDetailLayout listTitle="Matrices" list={list} detail={detail} onCloseDetail={cerrar} />;
}

export function MatricesScreen({ detailId }: { detailId?: string }) {
  const { pathname } = useLocation();
  if (pathname.includes('/matrices/nueva')) return <MatrizNuevaScreen />;
  if (pathname.includes('/matrices/editor')) return <MatrizEditorScreen />;
  if (pathname.includes('/matrices/plantilla/')) return <PlantillaActualizacionScreen />;
  return <MatricesListado detailId={detailId} />;
}
