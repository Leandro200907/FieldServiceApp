import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { session } from '../../api';
import { usePrototypeRead } from '../../hooks/usePrototypeRead';
import { LoadingState } from '../../ui/States';
import type { CambioPlantilla } from './matrizDraft';
import type { components } from '../../api/generated/modulo1';

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
    if (error || !response.ok) throw new Error('No se pudieron cargar plantillas');
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

  const traer = async () => {
    if (!copia) return;
    setBusy(true);
    setError(null);
    try {
      const elegidos = cambios.filter((c, i) => todos[key(c, i)]);
      const defsGlobales = plantillas.data?.definiciones || [];
      for (const c of elegidos) {
        if (c.tipo === 'agregado' && c.definicion_global_id) {
          const meta = defsGlobales.find(d => d.definicion_global_id === c.definicion_global_id);
          const body: components['schemas']['CopiarDefinicionGlobal'] = {
            definicion_global_id: c.definicion_global_id,
            locacion_id: meta?.categoria === 'induccion' ? copia.locacion_id : null,
          };
          await session.client.POST('/v1/comandos/copiar_definicion_global', {
            body,
            headers: { 'Idempotency-Key': crypto.randomUUID() },
          });
        }
      }
      const lineasBase = copia.lineas.map(l => ({
        requisito_definicion_id: l.requisito_definicion_id,
        clasificacion: l.clasificacion,
        bloqueante_durante_ejecucion: l.bloqueante_durante_ejecucion,
      }));
      const lineas: { requisito_definicion_id: string; clasificacion: 'bloqueante_duro' | 'excepcionable'; bloqueante_durante_ejecucion: boolean }[] = lineasBase.map(l => {
        const cambio = elegidos.find(c => c.requisito_definicion_id === l.requisito_definicion_id && c.clasificacion_destino);
        if (cambio?.clasificacion_destino) {
          return {
            ...l,
            clasificacion: cambio.clasificacion_destino as 'bloqueante_duro' | 'excepcionable',
            bloqueante_durante_ejecucion: cambio.bloqueante_durante_ejecucion_destino ?? l.bloqueante_durante_ejecucion,
          };
        }
        return l as { requisito_definicion_id: string; clasificacion: 'bloqueante_duro' | 'excepcionable'; bloqueante_durante_ejecucion: boolean };
      }).filter(l => !elegidos.some(c => c.tipo === 'quitado' && c.requisito_definicion_id === l.requisito_definicion_id));
      for (const c of elegidos.filter(x => x.tipo === 'agregado')) {
        if (!c.definicion_global_id) continue;
        const defs = await session.client.GET('/v1/consultas/definiciones_requisito', { params: { query: { activas: true, limit: 500, offset: 0 } } });
        const def = defs.data?.items.find(d => d.definicion_global_id === c.definicion_global_id);
        if (def && !lineas.some(l => l.requisito_definicion_id === def.requisito_definicion_id)) {
          lineas.push({
            requisito_definicion_id: def.requisito_definicion_id,
            clasificacion: (c.clasificacion_destino || 'bloqueante_duro') as 'bloqueante_duro' | 'excepcionable',
            bloqueante_durante_ejecucion: c.bloqueante_durante_ejecucion_destino ?? true,
          });
        }
      }
      const vigenteDesde = copia.vigente_desde;
      const pub = await session.client.POST('/v1/comandos/publicar_version_de_matriz', {
        body: {
          cliente_id: copia.cliente_id,
          locacion_id: copia.locacion_id!,
          tipo_servicio_id: copia.tipo_servicio_id,
          vigente_desde: vigenteDesde,
          lineas,
          fuente: `Actualización plantilla (${nTraer} cambios)`,
        },
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      });
      if (pub.error || !pub.response.ok) throw new Error('No se pudo publicar');
      navigate('/matrices');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al traer cambios');
    } finally {
      setBusy(false);
    }
  };

  if (plantillas.loading) return <LoadingState />;

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
