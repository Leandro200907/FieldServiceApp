import { describe, expect, it, vi } from 'vitest';

vi.mock('../src/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../src/api')>();
  return { ...actual, session: { client: { POST: vi.fn() } } };
});

import { session } from '../src/api';
import { altaDeSujeto } from '../src/features/legajos/altaSujetoApi';

const postMock = vi.mocked(session.client.POST);

describe('altaDeSujeto', () => {
  it('envía el nombre sólo para una persona y usa idempotencia', async () => {
    postMock.mockResolvedValueOnce({ data: { sujeto_id: 'persona-marina', legajo_id: 'legajo-1', eventos: [] }, error: undefined, response: new Response(null, { status: 200 }) });
    await altaDeSujeto({ tipo_sujeto: 'persona', identificador_natural: '123', nombre_apellido: 'Marina Pérez' });
    expect(postMock).toHaveBeenCalledWith('/v1/comandos/alta_de_sujeto', expect.objectContaining({
      body: { tipo_sujeto: 'persona', identificador_natural: '123', nombre_apellido: 'Marina Pérez' },
      headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }),
    }));
  });

  it('no agrega nombre_apellido para un vehículo', async () => {
    postMock.mockResolvedValueOnce({ data: { sujeto_id: 'vehiculo-aa123bb', legajo_id: 'legajo-2', eventos: [] }, error: undefined, response: new Response(null, { status: 200 }) });
    await altaDeSujeto({ tipo_sujeto: 'vehiculo', identificador_natural: 'AA123BB' });
    expect(postMock).toHaveBeenCalledWith('/v1/comandos/alta_de_sujeto', expect.objectContaining({
      body: { tipo_sujeto: 'vehiculo', identificador_natural: 'AA123BB' },
    }));
  });
});
