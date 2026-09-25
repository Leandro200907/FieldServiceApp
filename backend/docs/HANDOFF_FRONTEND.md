Warning: truncated output (original token count: 10035)
Total output lines: 485

# Handoff al frontend — Módulo 1 (backend v1)

Contrato HTTP del backend tal como está implementado. La fuente exacta de cada body y
respuesta es el OpenAPI vivo: `GET /docs` (Swagger) y `GET /openapi.json`. Este documento
explica lo que el OpenAPI no dice: autenticación, envelope de error, idempotencia,
semántica de concurrencia, roles y flujos.

Versión del backend: `app/version.py` (`VERSION`), migración esperada `0021_validacion_evidencia`.
Prefijo de todas las rutas: `/v1`.

## 0. Contrato OpenAPI versionado y tipos TypeScript

`docs/openapi.json` es el contrato canónico (claves ordenadas, sin hosts, `info.version` y
`info.x-migracion-head` = head de migraciones). Un test lo compara con el OpenAPI real de
la app: si el backend cambia el contrato, el archivo cambia en el mismo commit y el diff
muestra exactamente qué.

Regenerar (backend):

```bash
.venv/Scripts/python scripts/generar_openapi.py
```

Comprobar sin escribir: `scripts/generar_openapi.py --check` (sale 1 si difiere).

Generar tipos TypeScript (frontend), con [openapi-typescript](https://openapi-ts.dev):

```bash
npx openapi-typescript docs/openapi.json -o src/api/modulo1.d.ts
```

y un cliente tipado con `openapi-fetch`:

```ts
import createClient from "openapi-fetch";
import type { paths } from "./api/modulo1";
const api = createClient<paths>({ baseUrl: "/v1", headers: { Authorization: `Bearer ${token}` } });
const { data, error } = await api.GET("/v1/consultas/legajo", { params: { query: { sujeto_id: "p1" } } });
```

Todas las respuestas de error están tipadas con `components.schemas.ErrorEnvelope`; las
rutas protegidas declaran `security: bearerAuth`.

## 1. Autenticación

| Ruta | Body | Respuesta |
|---|---|---|
| `POST /v1/auth/login` | `{tenant_slug, email, password}` | `{access_token, refresh_token, token_type:"bearer", expires_in}` |
| `POST /v1/auth/refresh` | `{refresh_token}` | mismo par (rotación: el refresh viejo queda revo…9035 tokens truncated…tivos`, `empresa_no_se_propone`, `conflicto_con_dato_verificado` (409),
`recurso_no_custodiable`, `custodio_no_permitido`, `custodio_requerido`, `legajo_dado_de_baja`,
`excepcion_activa_duplicada` (409), `constancia_activa_duplicada` (409),
`custodia_vigente_duplicada` (409), `definicion_duplicada` (409), `sin_archivo`,
`archivo_ausente`, `archivo_vacio`, `archivo_demasiado_grande`, `conflicto_de_interes` (403:
un Supervisor operando sobre sí mismo — excepción, supervisión o custodia propias),
`archivo_pendiente_de_validacion` (409: la validación técnica del archivo todavía no
corrió), `archivo_invalido` (422: la validación técnica dio inválido), `usar_rechazar_propuesta`
(422: `invalidar_evidencia` sobre un documento todavía `declarado`).

## 8. Lo que el frontend NO tiene todavía (deudas conocidas del backend v1)
- No hay endpoints de gestión de usuarios (alta, desactivación, cambio ni restablecimiento
  de contraseña): tenant y usuarios se administran con `scripts/administracion.py`
  (crear-tenant, crear-usuario, desactivar-usuario, listar-usuarios). Un usuario
  desactivado no puede hacer login ni refresh, y su access token vigente deja de servir en
  el request siguiente (cada request protegido comprueba `activo`).
- Notificaciones: mail y Telegram reales dependen de que la plataforma tenga `SMTP_*` /
  `TELEGRAM_BOT_TOKEN` y de que el tenant habilite el canal; sin eso quedan en el log con
  traza. WhatsApp está diseñado (misma interfaz) pero no activo. Cola `validacion_evidencia`
  (lectura del contenido del archivo): segunda etapa.
- Publicación a Módulo 2: `PublicadorEnLog` (transporte real pendiente); el drenaje en sí ya
  tiene backoff, tope de reintentos y alerta obligatoria (notificación tipo
  `OutboxEstancado`, a `configuracion`, vía el mismo canal que cualquier otra alerta) si un
  evento se queda estancado.
- Storage: sólo backend local (`STORAGE_BACKEND=local`); el contrato ya es el de un bucket.

