import { describe, expect, it } from 'vitest';
import { notifyBandejaRevisionChanged, subscribeBandejaRevisionRefresh } from '../src/features/propuestas/bandejaRevisionRefresh';

describe('bandejaRevisionRefresh', () => {
  it('notifica a los suscriptores', () => {
    let n = 0;
    const unsub = subscribeBandejaRevisionRefresh(() => { n += 1; });
    notifyBandejaRevisionChanged();
    unsub();
    expect(n).toBe(1);
  });
});
