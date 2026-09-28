import { ApiFailure, parseApiError, session } from '../../api';
import type {
  BacklogQuery,
  CalendarQuery,
  DocumentationPlanningAccess,
  RadarLegajoQuery,
  RadarOcQuery,
} from './contracts';

// Adaptador real contra el backend — reemplaza a `temporaryMockAccess` cuando
// `featureFlags.documentationCalendarIntegration`/`radarDocumentationIntegration` están
// en `true`. Ningún parámetro de alcance/rol: el servidor lo resuelve del JWT
// (`alcance_de_sujetos`), estos tres GET no lo reciben (docs/HANDOFF_PROYECCION_ASTRA.md §1).
//
// `openapi-fetch` no lanza en errores HTTP — deja `error` poblado y `response` con el
// status real. Se traduce con el mismo `parseApiError`/`ApiFailure` que ya usa `session`,
// para que `ErrorState`/`usePrototypeRead` reciban siempre el mismo tipo de error en toda
// la app, venga de auth o de una consulta de negocio.
// Exportado para test (F-10, auditoría externa 2026-09-22): antes ningún test ejercitaba
// este adaptador real ni `unwrap` — sólo el mock. Ver tests/real-documentation-planning-access.test.ts.
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || !response.ok) {
    const requestId = response.headers.get('X-Request-ID') || crypto.randomUUID();
    throw new ApiFailure(parseApiError(error, response, requestId));
  }
  if (data === undefined) throw new ApiFailure(parseApiError(null, response, crypto.randomUUID()));
  return data;
}

export const realDocumentationPlanningAccess: DocumentationPlanningAccess = {
  async readCalendar(query: CalendarQuery) {
    return unwrap(
      session.client.GET('/v1/consultas/calendario_vigencias', {
        params: {
          query: {
            desde: query.from,
            hasta: query.to,
            tipo_sujeto: query.subjectKind,
            q: query.q,
            offset: query.offset,
            limit: query.limit,
          },
        },
      }),
    );
  },
  async readRadarBacklog(query: BacklogQuery) {
    return unwrap(
      session.client.GET('/v1/consultas/radar_documental_backlog', {
        params: {
          query: {
            desde: query.from,
            hasta: query.to,
            cliente_id: query.clienteId,
            locacion_id: query.locacionId,
            tipo_servicio_id: query.tipoServicioId,
            estado: query.estado,
            q: query.q,
            offset: query.offset,
            limit: query.limit,
          },
        },
      }),
    );
  },
  async readRadarOc(query: RadarOcQuery) {
    return unwrap(
      session.client.GET('/v1/consultas/radar_documental_oc', {
        params: { query: {
          oc_id: query.ocId,
          ...(query.offset === undefined ? {} : { offset: query.offset }),
          ...(query.limit === undefined ? {} : { limit: query.limit }),
        } },
      }),
    );
  },
  async readRadarLegajo(query: RadarLegajoQuery) {
    return unwrap(
      session.client.GET('/v1/consultas/radar_documental_oc/{oc_id}/legajos/{sujeto_id}', {
        params: { path: { oc_id: query.ocId, sujeto_id: query.sujetoId } },
      }),
    );
  },
};

