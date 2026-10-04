const listeners = new Set<() => void>();

export function subscribeBandejaRevisionRefresh(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function notifyBandejaRevisionChanged(): void {
  listeners.forEach(listener => { listener(); });
}
