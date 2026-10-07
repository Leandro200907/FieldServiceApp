import { session } from '../../api';
import { ApiFailure, parseApiError } from '../../api/errors';
import type { MatrizDraft } from './matrizDraft';
import { planPublicarMatriz } from './matrizPublishLogic';

export async function publicarMatrizDraft(draft: MatrizDraft): Promise<void> {
  const planes = planPublicarMatriz(draft);
  for (const plan of planes) {
    const requestId = crypto.randomUUID();
    const res = await session.client.POST(plan.path, {
      body: plan.body,
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    if (res.error !== undefined || !res.response.ok) {
      throw new ApiFailure(parseApiError(res.error, res.response, requestId));
    }
  }
}
