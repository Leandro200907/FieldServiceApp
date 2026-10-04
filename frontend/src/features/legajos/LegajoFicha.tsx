import { useState } from 'react';
import { session } from '../../api';
import { formatFecha } from '../documentation-planning/dates';
import { HistorialOperadoraPanel } from '../vencimientos/HistorialOperadoraPanel';
import { EstadoReferenciaLegajo } from '../../ui/EstadoReferencia';
import { FichaDato, FichaEncabezado } from '../../ui/ListDetailLayout';
import { StatusDot, variantFromEtiquetaVigencia } from '../../ui/StatusDot';
import { etiquetasEvidencia, textoPropuestaEnRevision } from '../../ui/evidenciaPresentacion';
import { formatDaysToExpiry } from '../../ui/formatDaysToExpiry';
import { OcsAfectadasLine } from '../../ui/OcsAfectadasLine';
import type { EvidenciaVigente } from '../mi-legajo/contracts';
import type { LegajoCompuesto } from '../mi-legajo/contracts';
import { formatDniIdentificador, subtituloLegajoPersona, tituloLegajoPersona } from './legajoDisplay';
import {
  contarBuckets,
  proximoVencimientoIso,
  resumenVencimientosTexto,
  todosLosDocumentos,
} from './legajoResumen';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { legajosAccess } from './access';
import { LegajoHistorialTab } from './LegajoHistorialTab';

const tipoRuta: Record<string, string> = {
  persona: 'Personas',
  vehiculo: 'Vehículos',
  equipo: 'Equipos',
  empresa: 'Empresa',
};

type Tab = 'documentos' | 'presentaciones' | 'historial';

function observacionFila(item: EvidenciaVigente): string {
  const parts: string[] = [];
  if (item.propuesta_en_revision) parts.push(textoPropuestaEnRevision(item.propuesta_en_revision));
  return parts.join(' · ') || '—';
}

export function LegajoFicha({ data, sujetoId }: { data: LegajoCompuesto; sujetoId: string; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('documentos');
  const [historialSel, setHistorialSel] = useState<{ operadoraId: string; requisitoId: string } | null>(null);
  const tz = session.getSnapshot().identity?.zona_horaria || 'America/Argentina/Buenos_Aires';
  const fmt = (iso: string) => formatFecha(iso, tz);
  const items = todosLosDocumentos(data);
  const revision = contarBuckets(items).en_revision;
  const buckets = {
    vencidos: data.resumen.vencidos,
    por_vencer: data.resumen.por_vencer ?? 0,
    vigentes: data.resumen.vigentes_hoy,
    en_revision: revision,
  };
  const enRegla = data.resumen.en_regla ?? 0;
  const total = data.resumen.total;
  const proximo = proximoVencimientoIso(items);
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
            <FichaDato label="Cumplimiento">{enRegla} de {total} en regla</FichaDato>
            <FichaDato label="Próximo vencimiento">{proximo ? fmt(proximo) : '—'}</FichaDato>
            <FichaDato label="OC afectadas">{ocsCount > 0 ? `${ocsCount} órden${ocsCount === 1 ? '' : 'es'}` : 'Ninguna'}</FichaDato>
            <FichaDato label="Resumen">{resumenVencimientosTexto(data.resumen.vencidos, data.resumen.por_vencer ?? 0)}</FichaDato>
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
            <div className="resumen-tarjeta"><strong>{buckets.en_revision}</strong><span>En revisión</span></div>
            <div className="resumen-tarjeta"><strong>{buckets.vigentes}</strong><span>Vigentes</span></div>
          </div>
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
                  const labels = etiquetasEvidencia(item);
                  return (
                    <tr key={item.id}>
                      <td>{item.requisito || 'Requisito sin nombre'}</td>
                      <td><span className="estado-tags">{labels.map(label => <StatusDot key={label} variant={variantFromEtiquetaVigencia(label)}>{label}</StatusDot>)}</span></td>
                      <td>{fmt(item.vigente_hasta)} · {formatDaysToExpiry(item.dias_para_vencer)}</td>
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
                      <td>—</td>
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
