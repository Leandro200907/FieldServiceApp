import { useState } from 'react';
import { session } from '../../api';
import { formatFecha } from '../documentation-planning/dates';
import { HistorialOperadoraPanel } from '../vencimientos/HistorialOperadoraPanel';
import { EstadoReferenciaLegajo } from '../../ui/EstadoReferencia';
import { FichaDato, FichaEncabezado } from '../../ui/ListDetailLayout';
import { StatusDot, variantFromEstadoFilaLegajo } from '../../ui/StatusDot';
import { formatDaysToExpiry } from '../../ui/formatDaysToExpiry';
import { OcsAfectadasLine } from '../../ui/OcsAfectadasLine';
import type { EvidenciaVigente } from '../mi-legajo/contracts';
import type { LegajoCompuesto } from '../mi-legajo/contracts';
import { formatDniIdentificador, subtituloLegajoPersona, tituloLegajoPersona } from './legajoDisplay';
import { textoCumplimientoExigidos } from './legajoCumplimiento';
import {
  contarPendientesRevision,
  proximoVencimientoIso,
  resumenExigidosTexto,
  todosLosDocumentos,
} from './legajoResumen';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { legajosAccess } from './access';
import { LegajoHistorialTab } from './LegajoHistorialTab';
import { RegistrarCompetenciaForm } from './RegistrarCompetenciaForm';
import { RegistrarInduccionForm } from './RegistrarInduccionForm';
import { abrirUrlDescargaAbsoluta } from '../propuestas/archivoPreview';
import { abrirCertificadoRespaldo } from './certificadoRespaldoApi';

const tipoRuta: Record<string, string> = {
  persona: 'Personas',
  vehiculo: 'Vehículos',
  equipo: 'Equipos',
  empresa: 'Empresa',
};

type Tab = 'documentos' | 'presentaciones' | 'historial';

type ItemExt = EvidenciaVigente & {
  observacion_operadora?: string;
  observacion_ficha?: string;
  estado_fila?: string;
  certificado_respaldo_documento_id?: string | null;
  no_exigido_backlog?: boolean;
  gestion_responsable?: string | null;
  faltante_exigido?: boolean;
};

function observacionFila(item: ItemExt): string {
  const parts: string[] = [];
  if (item.observacion_ficha) parts.push(item.observacion_ficha);
  if (item.observacion_operadora) parts.push(item.observacion_operadora);
  if (item.no_exigido_backlog) parts.push('No exigido por OC actuales');
  return parts.join(' · ') || '—';
}

export function LegajoFicha({ data, sujetoId, onRefresh }: { data: LegajoCompuesto; sujetoId: string; onClose: () => void; onRefresh?: () => void }) {
  const [tab, setTab] = useState<Tab>('documentos');
  const [historialSel, setHistorialSel] = useState<{ operadoraId: string; requisitoId: string } | null>(null);
  const [registrarInduccionId, setRegistrarInduccionId] = useState<string | null>(null);
  const [registrarCompetenciaId, setRegistrarCompetenciaId] = useState<string | null>(null);
  const [certificadoBusyId, setCertificadoBusyId] = useState<string | null>(null);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const roles = session.getSnapshot().identity?.roles ?? [];
  const esResponsable = roles.includes('responsable_legajos') || roles.includes('configuracion');
  const fmt = (iso: string) => formatFecha(iso, tz);
  const items = todosLosDocumentos(data) as ItemExt[];
  const pendientesRevision = contarPendientesRevision(items);
  const buckets = {
    vencidos: data.resumen.exigidos_vencidos ?? data.resumen.vencidos,
    por_vencer: data.resumen.exigidos_por_vencer ?? data.resumen.por_vencer ?? 0,
    vigentes: data.resumen.exigidos_vigentes ?? data.resumen.vigentes_hoy,
    sin_documento: data.resumen.exigidos_sin_documento ?? data.resumen.sin_documento ?? 0,
  };
  const proximo = proximoVencimientoIso(items.filter(i => i.estado_presentacion !== 'sin_documento'));
  const ocsCount = data.resumen.ocs_afectadas ?? 0;
  const tipo = data.legajo.tipo_sujeto;
  const espejo = usePrototypeRead(() => legajosAccess().readEspejoOperadora(sujetoId), [sujetoId]);
  const estadoLabels: Record<string, string> = {
    pendiente_envio: 'Pendiente de envío',
    pendiente_aceptacion: 'Pendiente de aceptación',
    rechazado: 'Rechazado',
    al_dia: 'Al día',
  };

  return (
    <>
      <FichaEncabezado
        breadcrumb={`Legajos / ${tipoRuta[tipo] || tipo}`}
        titulo={tituloLegajoPersona(data.legajo)}
        subtitulo={subtituloLegajoPersona(data.legajo) || undefined}
        datosClave={(
          <>
            {tipo === 'persona' && <FichaDato label="DNI" mono>{formatDniIdentificador(data.legajo.identificador_natural)}</FichaDato>}
            <FichaDato label="Alta">{fmt(data.legajo.creado_en.slice(0, 10))}</FichaDato>
            <FichaDato label="Cumplimiento">{textoCumplimientoExigidos(data)}</FichaDato>
            <FichaDato label="Próximo vencimiento">{proximo ? fmt(proximo) : '—'}</FichaDato>
            <FichaDato label="OC afectadas">{ocsCount > 0 ? `${ocsCount} ${ocsCount === 1 ? 'orden' : 'órdenes'}` : 'Ninguna'}</FichaDato>
            <FichaDato label="Resumen">{resumenExigidosTexto(data.resumen)}</FichaDato>
          </>
        )}
      />
      <div className="ficha-tabs" role="tablist">
        {(['documentos', 'presentaciones', 'historial'] as Tab[]).map(t => (
          <button key={t} type="button" role="tab" className={tab === t ? 'active' : ''} aria-selected={tab === t} onClick={() => setTab(t)}>
            {t === 'documentos' ? 'Documentos' : t === 'presentaciones' ? 'Presentaciones a operadoras' : 'Historial'}
          </button>
        ))}
      </div>

      {tab === 'documentos' && (
        <>
          <div className="resumen-tarjetas">
            <div className="resumen-tarjeta"><strong>{buckets.vencidos}</strong><span>Vencidos</span></div>
            <div className="resumen-tarjeta"><strong>{buckets.por_vencer}</strong><span>Por vencer</span></div>
            <div className="resumen-tarjeta"><strong>{buckets.vigentes}</strong><span>Vigentes</span></div>
            <div className="resumen-tarjeta"><strong>{buckets.sin_documento}</strong><span>Sin documento</span></div>
          </div>
          {pendientesRevision > 0 && (
            <p className="legajo-pendientes-revision muted">
              {pendientesRevision} pendiente{pendientesRevision === 1 ? '' : 's'} de revisar
            </p>
          )}
          <div className="read-table-scroll">
            <table className="read-table legajo-doc-table">
              <thead>
                <tr>
                  <th>Requisito</th>
                  <th>Estado</th>
                  <th>Vigencia</th>
                  <th>Observación</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => {
                  const estadoFila = item.estado_fila ?? '—';
                  return (
                    <tr key={item.id}>
                      <td>{item.requisito || 'Requisito sin nombre'}</td>
                      <td>
                        <span className="estado-tags">
                          <StatusDot variant={variantFromEstadoFilaLegajo(estadoFila)}>{estadoFila}</StatusDot>
                        </span>
                      </td>
                      <td>
                        {item.estado_presentacion === 'sin_documento'
                          ? '—'
                          : `${fmt(item.vigente_hasta)} · ${formatDaysToExpiry(item.dias_para_vencer)}`}
                      </td>
                      <td>
                        {(() => {
                          const obs = observacionFila(item);
                          const ocs = item.ocs_afectadas ?? [];
                          return (
                            <>
                              {obs !== '—' ? obs : null}
                              {ocs.length > 0 ? <div><OcsAfectadasLine ocs={ocs} hoyIso={data.hoy} timeZone={tz} /></div> : null}
                              {obs === '—' && !ocs.length ? '—' : null}
                            </>
                          );
                        })()}
                      </td>
                      <td>
                        {esResponsable && item.gestion_responsable === 'registrar_induccion' && (
                          <button
                            type="button"
                            className="button button-secondary button-small"
                            onClick={() => { setRegistrarCompetenciaId(null); setRegistrarInduccionId(item.id); }}
                          >
                            Registrar inducción
                          </button>
                        )}
                        {esResponsable && item.gestion_responsable === 'registrar_acreditacion' && (
                          <button
                            type="button"
                            className="button button-secondary button-small"
                            onClick={() => { setRegistrarInduccionId(null); setRegistrarCompetenciaId(item.id); }}
                          >
                            Registrar competencia
                          </button>
                        )}
                        {item.certificado_respaldo_documento_id && (
                          <button
                            type="button"
                            className="button button-secondary button-small"
                            disabled={certificadoBusyId === item.id}
                            onClick={() => {
                              setCertificadoBusyId(item.id);
                              void abrirCertificadoRespaldo(item.certificado_respaldo_documento_id as string)
                                .then(url => window.open(abrirUrlDescargaAbsoluta(url), '_blank', 'noopener,noreferrer'))
                                .finally(() => setCertificadoBusyId(null));
                            }}
                          >
                            Ver certificado
                          </button>
                        )}
                        {registrarInduccionId === item.id && (
                          <RegistrarInduccionForm
                            item={item}
                            personaId={sujetoId}
                            hoyIso={data.hoy}
                            onDone={() => { setRegistrarInduccionId(null); onRefresh?.(); }}
                            onCancel={() => setRegistrarInduccionId(null)}
                          />
                        )}
                        {registrarCompetenciaId === item.id && (
                          <RegistrarCompetenciaForm
                            item={item}
                            personaId={sujetoId}
                            hoyIso={data.hoy}
                            onDone={() => { setRegistrarCompetenciaId(null); onRefresh?.(); }}
                            onCancel={() => setRegistrarCompetenciaId(null)}
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {items.length === 0 && <p className="empty-inline">Sin documentación registrada.</p>}
          </div>
          <EstadoReferenciaLegajo />
        </>
      )}

      {tab === 'presentaciones' && (
        <>
          {espejo.loading ? <p>Cargando presentaciones…</p> : espejo.data?.items.length ? (
            <ul className="evidence-list">
              {espejo.data.items.map(item => (
                <li className="evidence-row" key={`${item.operadora_id}-${item.requisito_definicion_id}`}>
                  <span className="evidence-name">{item.requisito} · {item.operadora}</span>
                  <StatusDot variant={item.estado_operadora === 'al_dia' ? 'vigente' : item.estado_operadora === 'rechazado' ? 'vencido' : 'revision'}>{estadoLabels[item.estado_operadora as string] || item.estado_operadora}</StatusDot>
                  <small>{item.motivo || '—'}</small>
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={() => {
                      setHistorialSel({ operadoraId: item.operadora_id as string, requisitoId: item.requisito_definicion_id as string });
                      setTab('historial');
                    }}
                  >
                    Ver historial
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="empty-inline">Sin presentaciones registradas.</p>}
          <EstadoReferenciaLegajo incluirPresentaciones />
        </>
      )}

      {tab === 'historial' && (
        historialSel ? (
          <HistorialOperadoraPanel
            operadoraId={historialSel.operadoraId}
            sujetoId={sujetoId}
            requisitoDefinicionId={historialSel.requisitoId}
            onClose={() => setHistorialSel(null)}
          />
        ) : (
          <LegajoHistorialTab sujetoId={sujetoId} />
        )
      )}
    </>
  );
}
