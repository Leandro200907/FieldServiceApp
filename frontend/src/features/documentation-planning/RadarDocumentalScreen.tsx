import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiFailure, session } from '../../api';
import { ErrorState, LoadingState, Pending } from '../../ui/States';
import type { DetalleOcRadarResponse, ItemRadar, RadarState } from './contracts';
import { backlogAccess } from './access';
import { formatFecha } from './dates';
import { PAGE_SIZE, PaginationControls } from './PaginationControls';
import { documentationScopeFor } from './scope';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { RadarLegajoEvidenciaPanel } from './RadarLegajoEvidenciaPanel';
import { ListDetailLayout } from '../../ui/ListDetailLayout';
import { StatusDot, variantFromEtiquetaVigencia } from '../../ui/StatusDot';
import { estadoDocumentalOcLabels, labelEstadoDocumentalOc, labelEstadoDocumentalOcConMatriz, variantEstadoDocumentalOc } from '../../ui/documentalLabels';
import { etiquetaTipoSujeto } from '../../ui/tipoSujetoLabels';
import { lineaPersonaConDni } from '../legajos/legajoDisplay';
import { NotaAnalisisInformativo } from '../../ui/InformativoFooter';
import './planning.css';
import './radar.css';

function displayDate(value: string | null | undefined) {
  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  return value ? formatFecha(value, timeZone) : 'Sin fecha';
}

function displayInstant(value: string) {
  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  return formatFecha(value, timeZone);
}

function summaryLabel(row: ItemRadar) {
  const alerts = Object.values(row.resumen).reduce((total, item) => total + item.con_alertas, 0);
  const incomplete = Object.values(row.resumen).reduce((total, item) => total + item.incompletos, 0);
  if (alerts === 0 && incomplete === 0) return 'Sin alertas en los legajos observados';
  return [alerts > 0 ? `${alerts} con alerta${alerts === 1 ? '' : 's'}` : '', incomplete > 0 ? `${incomplete} incompleto${incomplete === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ');
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
function asText(value: unknown, fallback = 'Sin dato') { return typeof value === 'string' && value ? value : fallback; }
function asArray(value: unknown) { return Array.isArray(value) ? value : []; }

function estadoVariant(estado: string) {
  return variantEstadoDocumentalOc(estado);
}

function etiquetaOcContexto(parts: { operadora_nombre?: string | null; locacion_nombre?: string | null; tipo_servicio_nombre?: string | null }) {
  return [parts.operadora_nombre, parts.locacion_nombre, parts.tipo_servicio_nombre].filter(Boolean).join(' · ');
}

function contarAlertas(row: ItemRadar): number {
  const ciertas = row.alertas_ciertas?.length ?? 0;
  const caidas = (row.disponibilidad_por_tipo || []).reduce(
    (t, d) => t + ((d as { se_cae_en_ventana?: unknown[] }).se_cae_en_ventana?.length ?? 0),
    0,
  );
  return ciertas + caidas;
}

function textoMatrizUtilizada(
  raw: Record<string, unknown>,
  oc: Record<string, unknown>,
  timeZone: string,
): string {
  const contexto = [oc.operadora_nombre, oc.locacion_nombre, oc.tipo_servicio_nombre].filter(Boolean).join(' · ');
  const version = raw.version;
  const desdeRaw = typeof raw.vigente_desde === 'string' ? raw.vigente_desde : raw.desde;
  const desde = typeof desdeRaw === 'string' ? formatFecha(desdeRaw, timeZone) : '';
  return `${contexto || 'Matriz'} — Versión ${version} — vigente desde ${desde}`;
}

function DetailPanel({ detail, onLegajo, onOffsetChange }: { detail: DetalleOcRadarResponse; onLegajo: (sujetoId: string) => void; onOffsetChange: (offset: number) => void }) {
  const oc = asRecord(detail.oc);
  const timeZone = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  return (
    <div aria-live="polite">
      <p className="ficha-breadcrumb">Radar de OC / Detalle</p>
      <h2 className="ficha-titulo">{asText(oc?.clave_origen, 'Orden de compra')}</h2>
      {oc && etiquetaOcContexto(oc) && <p className="ficha-subtitulo">{etiquetaOcContexto(oc)}</p>}
      <p className="ficha-subtitulo">{displayDate(asText(oc?.vigencia_desde, ''))} — {displayDate(asText(oc?.vigencia_hasta, ''))}</p>
      <StatusDot variant={estadoVariant(detail.estado_documental)}>{labelEstadoDocumentalOc(detail.estado_documental)}</StatusDot>
      <p className="detail-note">{detail.advertencia}</p>
      <div>
        <strong>Matrices y requisitos considerados</strong>
        {detail.matrices_utilizadas.length > 0 ? (
          <ul>
            {detail.matrices_utilizadas.map((m, i) => (
              <li key={i}>{textoMatrizUtilizada(asRecord(m) || {}, oc || {}, timeZone)}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            Falta cargar la matriz de {[oc?.operadora_nombre, oc?.locacion_nombre].filter(Boolean).join(' · ') || 'esta OC'}.
          </p>
        )}
        {detail.requisitos_particulares.length > 0 && (
          <p>{detail.requisitos_particulares.length} requisito{detail.requisitos_particulares.length === 1 ? '' : 's'} particular{detail.requisitos_particulares.length === 1 ? '' : 'es'}.</p>
        )}
        {(detail.disponibilidad_por_tipo?.length ?? 0) > 0 && <p><strong>Habilitación por tipo:</strong> {detail.disponibilidad_por_tipo!.map(d => d.texto).join(' · ')}</p>}
        <strong>Legajos observados por tipo</strong>
        <ul>
          {detail.grupos.map((rawGroup, groupIndex) => {
            const group = asRecord(rawGroup);
            const legajos = asArray(group?.legajos);
            const total = typeof group?.total === 'number' ? group.total : legajos.length;
            const tipo = asText(group?.tipo_sujeto);
            return <li key={`${tipo}-${groupIndex}`}>
              <strong>{etiquetaTipoSujeto(tipo, total)}</strong>
              {group?.sin_legajos_requeridos === true && <strong> · Sin legajos habilitados visibles para este tipo</strong>}
              {legajos.length > 0 && <ul>{legajos.map((rawLegajo, index) => {
                const legajo = asRecord(rawLegajo);
                const sujetoId = asText(legajo?.sujeto_id, '');
                const estadoLeg = asText(legajo?.estado_documental, '');
                return <li key={sujetoId || index}>
                  {lineaPersonaConDni({
                    tipo_sujeto: asText(legajo?.tipo_sujeto, 'persona'),
                    nombre_apellido: typeof legajo?.nombre_apellido === 'string' ? legajo.nombre_apellido : null,
                    identificador_natural: asText(legajo?.identificador_natural, sujetoId),
                    sujeto_id: sujetoId,
                  })}
                  {' · '}
                  <StatusDot variant={variantEstadoDocumentalOc(estadoLeg)}>{labelEstadoDocumentalOc(estadoLeg)}</StatusDot>
                  {sujetoId && <button type="button" className="text-button detail-link" onClick={() => onLegajo(sujetoId)}>Ver evidencia</button>}
                </li>;
              })}</ul>}
            </li>;
          })}
        </ul>
        <PaginationControls offset={detail.offset} limit={detail.limit} total={detail.total_legajos} onOffsetChange={onOffsetChange} />
      </div>
    </div>
  );
}

export function RadarDocumentalScreen({ roles, detailId }: { roles: readonly string[]; detailId?: string }) {
  const navigate = useNavigate();
  const resolved = documentationScopeFor(roles);
  const [selected, setSelected] = useState<string | null>(detailId ?? null);
  const [selectedLegajo, setSelectedLegajo] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [detailOffset, setDetailOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [state, setState] = useState<RadarState | ''>('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [appliedState, setAppliedState] = useState<RadarState | ''>('');

  useEffect(() => { setSelected(detailId ?? null); setSelectedLegajo(null); }, [detailId]);

  const radar = usePrototypeRead(
    () => backlogAccess().readRadarBacklog({ q: appliedSearch || undefined, estado: appliedState ? [appliedState] : undefined, offset, limit: PAGE_SIZE }),
    [appliedSearch, appliedState, offset],
  );
  const detail = usePrototypeRead(() => selected ? backlogAccess().readRadarOc({ ocId: selected, offset: detailOffset, limit: PAGE_SIZE }) : Promise.resolve(null), [selected, detailOffset]);
  const legajo = usePrototypeRead(
    () => selected && selectedLegajo ? backlogAccess().readRadarLegajo({ ocId: selected, sujetoId: selectedLegajo }) : Promise.resolve(null),
    [selected, selectedLegajo],
  );

  if (!resolved || resolved === 'technician') return <Pending title="Sin acceso a esta vista">El radar está disponible para responsables de legajos y supervisores.</Pending>;

  function applyFilters() {
    setOffset(0);
    navigate('/radar-documental');
    setSelectedLegajo(null);
    setDetailOffset(0);
    setAppliedSearch(search.trim());
    setAppliedState(state);
  }

  const abrirOc = (ocId: string) => navigate(`/radar-documental/${ocId}`);
  const cerrar = () => { navigate('/radar-documental'); setSelectedLegajo(null); };

  const list = (
    <>
      <div className="form-field"><label htmlFor="radar-search">Buscar OC</label><input id="radar-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Número o referencia" /></div>
      <div className="form-field"><label htmlFor="radar-state">Estado documental</label><select id="radar-state" value={state} onChange={event => setState(event.target.value as RadarState | '')}><option value="">Todos</option>{Object.entries(estadoDocumentalOcLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      <button type="button" className="button button-primary" onClick={applyFilters}>Aplicar filtros</button>
      {radar.loading ? <LoadingState /> : radar.error ? <ErrorState message={radar.error.message} requestId={radar.error instanceof ApiFailure && radar.error.detail.referenceSource === 'server' ? radar.error.detail.requestId : undefined} /> : (
        <>
          <p className="muted" style={{ marginTop: 12 }}>{displayDate(radar.data?.desde)} — {displayDate(radar.data?.hasta)} · {radar.data?.total ?? 0} OC</p>
          {radar.data?.items.map(row => (
            <button key={row.oc_id} type="button" className={`list-item-button${selected === row.oc_id ? ' selected' : ''}`} onClick={() => abrirOc(row.oc_id)}>
              <span>
                <span className="list-item-primary">{row.clave_origen}</span>
                {etiquetaOcContexto(row) && <span className="list-item-secondary">{etiquetaOcContexto(row)}</span>}
                <span className="list-item-secondary">{displayDate(row.vigencia_desde)} — {displayDate(row.vigencia_hasta)}</span>
                {contarAlertas(row) > 0 && <span className="list-item-secondary">{contarAlertas(row)} alerta{contarAlertas(row) === 1 ? '' : 's'}</span>}
              </span>
              <StatusDot variant={estadoVariant(row.estado_documental)}>{labelEstadoDocumentalOcConMatriz(row.estado_documental, row)}</StatusDot>
            </button>
          ))}
          {radar.data?.items.length === 0 && <p className="empty-inline">No hay OC visibles para estos filtros.</p>}
          {radar.data && <PaginationControls offset={radar.data.offset} limit={radar.data.limit} total={radar.data.total} onOffsetChange={value => { setOffset(value); cerrar(); }} />}
        </>
      )}
    </>
  );

  const detailPane = selected && (detail.loading ? <LoadingState /> : detail.error ? <ErrorState message={detail.error.message} /> : detail.data && (
    <>
      <DetailPanel detail={detail.data} onLegajo={setSelectedLegajo} onOffsetChange={value => { setDetailOffset(value); setSelectedLegajo(null); }} />
      {selectedLegajo && (legajo.loading ? <LoadingState /> : legajo.error ? <ErrorState message={legajo.error.message} /> : legajo.data && <RadarLegajoEvidenciaPanel data={legajo.data} />)}
    </>
  ));

  return (
    <>
      <ListDetailLayout listTitle="Órdenes de compra" list={list} detail={detailPane} onCloseDetail={cerrar} />
      <NotaAnalisisInformativo />
    </>
  );
}
