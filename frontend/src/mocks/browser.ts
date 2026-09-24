import { setupWorker } from 'msw/browser';
import { http, HttpResponse } from 'msw';
import fixtures from './fixtures.json';

// Synthetic fixtures only. No business handler, inferred DTO or proposed endpoint.
function fixture(name: string) {
  const result = fixtures.fixtures.find(value => value.name === name);
  if (!result) throw new Error('Unknown fixture');
  return result;
}
let activeRole = 'tecnico';
const roles = ['configuracion', 'responsable_legajos', 'supervisor', 'tecnico'];
export const worker = setupWorker(
  http.post('/v1/auth/login', async ({ request }) => {
    const body = await request.json() as { email?: unknown };
    const prefix = typeof body?.email === 'string' ? body.email.split('@')[0] : '';
    activeRole = roles.includes(prefix) ? prefix : 'tecnico';
    return HttpResponse.json(fixture('login-200').body);
  }),
  http.post('/v1/auth/refresh', () => HttpResponse.json(fixture('refresh-200').body)),
  http.get('/v1/auth/yo', () => HttpResponse.json(fixture(`yo-200-${activeRole}`).body)),
  // Logout's success is unstructured. Do not invent revocado:true. Return a
  // contracted error so the UI exercises local logout with remote uncertainty.
  http.post('/v1/auth/logout', () => HttpResponse.json({ error: { codigo: 'error_interno', mensaje: 'Escenario de prueba: revocación remota no simulada.', detalles: null, request_id: 'SYNTHETIC_LOGOUT_UNCONFIRMED' } }, { status: 500 })),
);
