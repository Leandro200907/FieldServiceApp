import { useEffect, useState } from 'react';

// Compartido entre features (antes vivía sólo en documentation-planning; mi-legajo lo
// necesita igual, sin duplicar el hook).
export function usePrototypeRead<T>(load: () => Promise<T>, dependencies: readonly unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: Error; loading: boolean }>({ loading: true });
  useEffect(() => {
    let active = true;
    setState({ loading: true });
    void load().then(data => { if (active) setState({ data, loading: false }); }, error => { if (active) setState({ error: error instanceof Error ? error : new Error('Error desconocido'), loading: false }); });
    return () => { active = false; };
    // The caller owns the stable dependency list for the replaceable access query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies);
  return state;
}
