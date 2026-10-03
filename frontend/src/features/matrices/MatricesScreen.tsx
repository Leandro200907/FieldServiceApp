import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiFailure, session } from '../../api';
import { ErrorState, LoadingState } from '../../ui/States';
import { PAGE_SIZE, PaginationControls } from '../documentation-planning/PaginationControls';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { matricesAccess } from './access';
import type { MatrizItem } from './contracts';
import { ListDetailLayout } from '../../ui/ListDetailLayout';
import { StatusDot } from '../../ui/StatusDot';
import { formatFecha } from '../documentation-planning/dates';
import '../documentation-planning/planning.css';
import './matrices.css';

const clasificacionLabels: Record<string, string> = { bloqueante_duro: 'Bloqueante duro', excepcionable: 'Excepcionable' };

export function MatricesScreen({ detailId }: { detailId?: string }) {
  const navigate = useNavigate();
  const [clienteId, setClienteId] = useState('');
  const [soloVigentes, setSoloVigentes] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<MatrizItem | null>(null);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const fmt = (iso: string) => formatFecha(iso, tz);
  const soloLectura = !session.getSnapshot().identity?.roles.includes('configuracion');

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

  const list = (
    <>
      {soloLectura && <p className="muted" role="note">Solo lectura: la edición de matrices corresponde al rol Configuración (D7).</p>}
      <div className="form-field"><label htmlFor="matriz-cliente">Cliente</label><input id="matriz-cliente" className="font-mono" value={clienteId} onChange={event => { setClienteId(event.target.value); setOffset(0); }} placeholder="Identificador de cliente" /></div>
      <div className="form-field"><label htmlFor="matriz-vigentes"><input id="matriz-vigentes" type="checkbox" checked={soloVigentes} onChange={event => { setSoloVigentes(event.target.checked); setOffset(0); }} /> Solo vigentes hoy</label></div>
      {versiones.loading ? <LoadingState /> : versiones.error ? <ErrorState message={versiones.error.message} requestId={versiones.error instanceof ApiFailure && versiones.error.detail.referenceSource === 'server' ? versiones.error.detail.requestId : undefined} /> : (
        <>
          {versiones.data?.items.map(item => (
            <button key={item.matriz_version_id} type="button" className={`list-item-button${selected?.matriz_version_id === item.matriz_version_id ? ' selected' : ''}`} onClick={() => abrir(item)}>
              <span>
                <span className="list-item-primary">{item.cliente_id}</span>
                <span className="list-item-secondary font-mono">{item.locacion_id} · {item.tipo_servicio_id}</span>
              </span>
              <StatusDot variant="vigente">v{item.version}</StatusDot>
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
      <h2 className="ficha-titulo">Versión {detalle.data.version}</h2>
      <p className="ficha-subtitulo font-mono">{detalle.data.cliente_id} / {detalle.data.locacion_id} / {detalle.data.tipo_servicio_id}</p>
      <p className="muted">Consultada al {fmt(detalle.data.fecha_consultada)} · vigencia desde {fmt(selected.vigente_desde)} — {selected.vigente_hasta ? fmt(selected.vigente_hasta) : 'sin fin'}</p>
      <ul className="evidence-list">
        {detalle.data.lineas.map(linea => (
          <li key={linea.requisito_definicion_id} className="evidence-row">
            <span className="evidence-name">{linea.requisito || 'Requisito sin nombre'}</span>
            <StatusDot variant={linea.clasificacion === 'bloqueante_duro' ? 'por_vencer' : 'neutral'}>{clasificacionLabels[linea.clasificacion] || linea.clasificacion}</StatusDot>
            <small>{linea.tipo_sujeto_aplicable || 'Cualquier sujeto'} · {linea.categoria || 'Sin categoría'}</small>
          </li>
        ))}
      </ul>
      {detalle.data.lineas.length === 0 && <p className="empty-inline">Esta versión no tiene líneas.</p>}
    </>
  ));

  return <ListDetailLayout listTitle="Matrices" list={list} detail={detail} onCloseDetail={cerrar} />;
}
