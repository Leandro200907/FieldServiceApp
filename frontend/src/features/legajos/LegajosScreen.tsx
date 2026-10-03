import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiFailure } from '../../api';
import { ErrorState, LoadingState } from '../../ui/States';
import { ListDetailLayout } from '../../ui/ListDetailLayout';
import { StatusDot } from '../../ui/StatusDot';
import { subtituloLegajoPersona, tituloLegajoPersona } from './legajoDisplay';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { legajosAccess } from './access';
import type { SubjectKind } from './contracts';
import { LegajoFicha } from './LegajoFicha';
import '../documentation-planning/planning.css';

const tipoLabels: Record<string, string> = { persona: 'Persona', vehiculo: 'Vehículo', equipo: 'Equipo', empresa: 'Empresa' };
const TIPO_OPTIONS: SubjectKind[] = ['persona', 'vehiculo', 'equipo', 'empresa'];

function estadoListaSujeto(activo: boolean) {
  return activo ? <StatusDot variant="vigente">Activo</StatusDot> : <StatusDot variant="vencido">Dado de baja</StatusDot>;
}

export function LegajosScreen({ detailId }: { detailId?: string }) {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [tipoSujeto, setTipoSujeto] = useState<SubjectKind | ''>('');
  const selected = detailId ?? null;
  const search = usePrototypeRead(() => legajosAccess().searchSujetos({ q: q || undefined, tipoSujeto: tipoSujeto || undefined, limit: 20 }), [q, tipoSujeto]);
  const legajo = usePrototypeRead(() => selected ? legajosAccess().readLegajo(selected) : Promise.resolve(null), [selected]);

  const abrir = (sujetoId: string) => navigate(`/legajos/${sujetoId}`);
  const cerrar = () => navigate('/legajos');

  const list = (
    <>
      <div className="form-field"><label htmlFor="legajo-search">Buscar</label><input id="legajo-search" type="search" value={q} onChange={event => setQ(event.target.value)} placeholder="Nombre o identificador" /></div>
      <div className="form-field"><label htmlFor="legajo-tipo">Tipo</label><select id="legajo-tipo" value={tipoSujeto} onChange={event => setTipoSujeto(event.target.value as SubjectKind | '')}><option value="">Todos</option>{TIPO_OPTIONS.map(tipo => <option key={tipo} value={tipo}>{tipoLabels[tipo]}</option>)}</select></div>
      {search.loading ? <LoadingState /> : search.error ? <ErrorState message={search.error.message} requestId={search.error instanceof ApiFailure && search.error.detail.referenceSource === 'server' ? search.error.detail.requestId : undefined} /> : (
        <>
          {search.data?.items.map(sujeto => {
            const activo = !sujeto.dado_de_baja_en;
            return (
              <button
                key={sujeto.sujeto_id}
                type="button"
                className={`list-item-button${selected === sujeto.sujeto_id ? ' selected' : ''}`}
                onClick={() => abrir(sujeto.sujeto_id)}
              >
                <span>
                  <span className="list-item-primary">{tituloLegajoPersona(sujeto)}</span>
                  <span className="list-item-secondary font-mono">{subtituloLegajoPersona(sujeto) || tipoLabels[sujeto.tipo_sujeto]}</span>
                </span>
                {estadoListaSujeto(activo)}
              </button>
            );
          })}
          {search.data?.items.length === 0 && <p className="empty-inline">Sin sujetos que coincidan con la búsqueda.</p>}
        </>
      )}
    </>
  );

  const detail = selected && (legajo.loading ? <LoadingState /> : legajo.error ? (
    <ErrorState message={legajo.error.message} requestId={legajo.error instanceof ApiFailure && legajo.error.detail.referenceSource === 'server' ? legajo.error.detail.requestId : undefined} />
  ) : legajo.data ? <LegajoFicha data={legajo.data} sujetoId={selected} onClose={cerrar} /> : null);

  return <ListDetailLayout listTitle="Legajos" list={list} detail={detail} onCloseDetail={cerrar} />;
}
