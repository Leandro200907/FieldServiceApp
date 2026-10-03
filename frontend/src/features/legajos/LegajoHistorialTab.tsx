import { useEffect, useState } from 'react';
import { safeFailure } from '../../api';
import { ErrorState, LoadingState } from '../../ui/States';
import { HistorialOperadoraPanel } from '../vencimientos/HistorialOperadoraPanel';
import { legajosAccess } from './access';

type EspejoItem = {
  operadora_id: string;
  operadora: string;
  requisito: string;
  requisito_definicion_id: string;
};

export function LegajoHistorialTab({ sujetoId }: { sujetoId: string }) {
  const [items, setItems] = useState<EspejoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof safeFailure> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void legajosAccess()
      .readEspejoOperadora(sujetoId)
      .then(data => {
        if (cancelled) return;
        setItems((data.items ?? []) as EspejoItem[]);
      })
      .catch(err => { if (!cancelled) setError(safeFailure(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sujetoId]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error.message} />;
  if (!items.length) return <p className="empty-inline">Sin historial de presentaciones ante operadoras.</p>;

  return (
    <div className="legajo-historial-stack">
      {items.map(item => (
        <HistorialOperadoraPanel
          key={`${item.operadora_id}-${item.requisito_definicion_id}`}
          embedded
          operadoraId={item.operadora_id}
          sujetoId={sujetoId}
          requisitoDefinicionId={item.requisito_definicion_id}
          tituloExtra={`${item.requisito} · ${item.operadora}`}
        />
      ))}
    </div>
  );
}
