import { useEffect, useState } from 'react';

export type PrototypeReadState<T> = { data?: T; error?: Error; loading: boolean };

export function beginReload<T>(prev: PrototypeReadState<T>): PrototypeReadState<T> {
  return { data: prev.data, loading: true };
}

export function esCargaInicial(query: { loading: boolean; data?: unknown }): boolean {
  return query.loading && query.data === undefined;
}

// Compartido entre features (antes vivía sólo en documentation-planning; mi-legajo lo
// necesita igual, sin duplicar el hook).
export function usePrototypeRead<T>(load: () => Promise<T>, dependencies: readonly unknown[]) {
  const [state, setState] = useState<PrototypeReadState<T>>({ loading: true });
  useEffect(() => {
    let active = true;
    setState(prev => beginReload(prev));
    void load().then(data => { if (active) setState({ data, loading: false }); }, error => { if (active) setState({ error: error instanceof Error ? error : new Error('Error desconocido'), loading: false }); });
    return () => { active = false; };
    // The caller owns the stable dependency list for the replaceable access query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);
  return state;
}
