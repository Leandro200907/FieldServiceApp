import { ApiFailure, parseApiError, session } from '../../api';
import type {
  BacklogQuery,
  CalendarQuery,
  DocumentationPlanningAccess,
  ProjectionDetailQuery,
} from './contracts';

// Adaptador real contra el backend — reemplaza a `temporaryMockAccess` cuando
// `featureFlags.documentationCalendarIntegration`/`backlogDocumentationIntegration` están
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
  async readBacklogProjection(query: BacklogQuery) {
    return unwrap(
      session.client.GET('/v1/consultas/proyeccion_documental_backlog', {
        params: {
          query: {
            estado_oc: query.estadoOc,
            estado: query.estado,
            horizonte_dias: query.horizonteDias,
            offset: query.offset,
            limit: query.limit,
          },
        },
      }),
    );
  },
  async readProjectionDetail(query: ProjectionDetailQuery) {
    return unwrap(
      session.client.GET('/v1/consultas/proyeccion_documental', {
        params: {
          query: {
            commitment_id: query.commitmentId,
            desde: query.desde,
            hasta: query.hasta,
            detalle: query.detalle,
          },
        },
      }),
    );
  },
};
