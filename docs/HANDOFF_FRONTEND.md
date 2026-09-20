# Handoff al frontend — Módulo 1 (backend v1)

Contrato HTTP del backend tal como está implementado. La fuente exacta de cada body y
respuesta es el OpenAPI vivo: `GET /docs` (Swagger) y `GET /openapi.json`. Este documento
explica lo que el OpenAPI no dice: autenticación, envelope de error, idempotencia,
semántica de concurrencia, roles y flujos.

Versión del backend: `app/version.py` (`VERSION`), migración esperada `0017_alertas_vencimiento`.
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
| `POST /v1/auth/refresh` | `{refresh_token}` | mismo par (rotación: el refresh viejo queda revocado) |
| `POST /v1/auth/logout` | `{refresh_token}` (con Bearer) | `{revocado: bool}` |
| `GET /v1/auth/yo` | — | `{tenant_id, usuario_id, roles[], sujeto_id}` |

- Todo lo demás exige `Authorization: Bearer <access_token>`. Sin token o vencido: **401**
  `no_autenticado`. Rol insuficiente: **403** `prohibido` (`detalles.roles_requeridos`).
- **Cada request protegido comprueba el estado actual del usuario en la base**: si fue
  desactivado (o borrado), el access token vigente responde 401 genérico de inmediato en
  todas las instancias; refresh y login también 401. Ante un 401 inesperado con token
  aún no vencido, el cliente debe cerrar sesión (no reintentar el refresh en loop).
- Credenciales malas: siempre 401 genérico (no se distingue slug/email/contraseña).
- **Contraseña: máximo 72 bytes UTF-8** (no caracteres). Más largo → 422 `validacion` con
  `loc: ["body","password"]`; el backend nunca trunca. Un 72-caracteres con acentos puede
  exceder el límite: validalo en bytes también en el cliente.
- El tenant nunca viaja en headers ni en el body de comandos: sale del token.
- Roles: `configuracion`, `responsable_legajos`, `supervisor`, `tecnico`. Un usuario puede
  tener varios. El técnico tiene `sujeto_id` (su legajo).

## 2. Envelope de error y `request_id`

Todo error, de cualquier status, tiene esta forma exacta:

```json
{"error": {"codigo": "...", "mensaje": "...", "detalles": {...} | [...] | null, "request_id": "..."}}
```

- `codigo` es estable (lista en §7); `mensaje` es humano y puede cambiar.
- **`request_id`**: viene también en el header `X-Request-ID` de *todas* las respuestas
  (éxito o error). Si el cliente manda `X-Request-ID`, se respeta (≤ 64 chars imprimibles);
  si no, se genera. Mostralo en pantallas de error para correlacionar con el log del servidor.
- **500** `error_interno`: mensaje genérico, nunca detalle. Reportá el `request_id`.
- **422** `validacion`: `detalles` es una lista `[{loc, tipo, mensaje}]`. **Nunca incluye
  el valor recibido** (`input`): no lo esperes.
- **409** `conflicto_concurrencia`: la base rechazó por una restricción que la lógica no
  anticipó (carrera). Reintentable.

## 3. Idempotencia (`Idempotency-Key`) en todos los `POST /v1/comandos/*`

- Header opcional `Idempotency-Key` (recomendado en todo comando disparado por un click).
  Ámbito: **(tenant, usuario, clave)**. Otro usuario con la misma clave no obtiene tu replay.
- Misma clave + mismo body → **replay** de la respuesta original (mismo status y JSON).
- Misma clave + body distinto → **409** `clave_idempotencia_reutilizada`, siempre.
- Misma clave mientras la primera ejecución todavía corre → **409** `operacion_en_proceso`
  (reintentar en unos segundos).
- `importar_lote` deriva la clave del `lote_id` del body (`lote:<id>`); repetir el mismo
  lote con otro contenido → **409** `lote_contenido_distinto`.
- Antes de reproducir un replay se vuelve a verificar la autorización actual (un
  supervisor que perdió a la persona de su universo recibe 403/404, no el replay).

## 4. Rutas

### 4.1 Salud (sin token)
- `GET /v1/salud/vivo` — liveness `{ok, version}`.
- `GET /v1/salud/listo` — readiness: `{ok, version, chequeos:{db, migracion, storage, worker}}`;
  200 si todo `ok`, 503 si no. Valores cerrados: `ok`, `no_disponible`, `atrasada`,
  `adelantada`, `desconocida`, `sin_latido`, `vencido`. Sin JWT, sin detalles internos.

### 4.2 Comandos de legajos y evidencia (`POST /v1/comandos/…`)
| Ruta | Rol | Body (campos principales) |
|---|---|---|
| `POST /v1/comandos/alta_de_sujeto` | responsable_legajos | `{tipo_sujeto: empresa\|persona\|vehiculo\|equipo, identificador_natural, sujeto_id?}` |
| `POST /v1/comandos/baja_de_sujeto` | responsable_legajos | `{sujeto_id}` |
| `POST /v1/comandos/cargar_documento` | responsable_legajos | `{sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, numero?, origen?, estado_confirmacion?}` → `{documento_id, eventos[]}` |
| `POST /v1/comandos/proponer_documento` | tecnico (sobre su propio legajo) | `{sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, numero?}` |
| `POST /v1/comandos/confirmar_documento` | responsable_legajos | `{documento_id}` |
| `POST /v1/comandos/rechazar_propuesta` | responsable_legajos | `{documento_id, motivo?}` |
| `POST /v1/comandos/registrar_acreditacion_de_competencia` | responsable_legajos | `{persona_id, requisito_definicion_id, vigente_desde, vigente_hasta, evidencias[]}` |
| `POST /v1/comandos/registrar_induccion` | responsable_legajos | `{persona_id, locacion_id, requisito_definicion_id, vigente_desde, vigente_hasta, evidencia (documento_id)}` |
| `POST /v1/comandos/importar_lote` | responsable_legajos | `{lote_id, origen?, filas:[{sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, numero?, estado_confirmacion?}], hash_archivo?}` — las filas viajan crudas: una fila con UUID/fecha/campo inválido se rechaza sola (`fila_invalida` en `detalle_filas_rechazadas`) y las demás se aplican; el lote entero sólo es 422 si `filas` no es una lista o está vacía (ver `lote_contenido_distinto`) |
| `POST /v1/comandos/revertir_lote` | responsable_legajos | `{lote_id}` |
| `POST /v1/comandos/asignar_supervisor` | configuracion, responsable_legajos | `{sujeto_id, supervisor_usuario_id, desde?}` |
| `POST /v1/comandos/reasignar_supervisor` | configuracion, responsable_legajos | `{sujeto_id, supervisor_usuario_id, desde?}` |
| `POST /v1/comandos/preparar_subida_de_evidencia` | responsable_legajos, tecnico | `{documento_id, nombre_archivo, content_type}` → `{url_subida, content_type, max_bytes, expira_en_seg}` |
| `POST /v1/comandos/confirmar_subida_de_evidencia` | responsable_legajos, tecnico | `{documento_id}` → `{checksum_sha256, bytes, eventos[]}` |

**Flujo de evidencia**: `preparar_subida` → el navegador hace `PUT <url_subida>` con el
archivo crudo y el mismo `Content-Type` (sin JWT: la URL firmada es el permiso; vence en
`expira_en_seg`; `max_bytes` se exige) → `confirmar_subida` (mide el archivo real; 422
`archivo_ausente` / `archivo_vacio` / `archivo_demasiado_grande` si no cierra). Descarga:
`GET /v1/storage/documentos/{documento_id}/url` (roles responsable/supervisor/técnico, según
alcance) → `{url}` efímera → `GET <url>`.

- `PUT /v1/storage/{firma}` y `GET /v1/storage/{firma}` son el "bucket" de desarrollo; en
  producción la URL firmada apuntará al storage real con el mismo flujo.

### 4.3 Comandos de requisitos y OC
| Ruta | Rol | Body |
|---|---|---|
| `POST /v1/comandos/dar_de_alta_definicion_de_requisito` | configuracion | `{nombre, categoria: documento\|competencia\|induccion, tipo_sujeto_aplicable, locacion_id?, definicion_global_id?, plazo_retencion_archivo_dias?}` |
| `POST /v1/comandos/dar_de_baja_definicion_de_requisito` | configuracion | `{requisito_definicion_id}` |
| `POST /v1/comandos/publicar_version_de_matriz` | configuracion | `{cliente_id, locacion_id, tipo_servicio_id, vigente_desde, lineas:[{requisito_definicion_id, clasificacion, bloqueante_durante_ejecucion}], fuente?, archivo_de_respaldo?, autor?}` |
| `POST /v1/comandos/copiar_definicion_global` | configuracion | `{definicion_global_id, locacion_id?}` (obligatoria si la definición global es inducción) → `{requisito_definicion_id, copiada_de_version}`; repetida → 409 `definicion_duplicada` |
| `POST /v1/comandos/copiar_matriz_global` | configuracion | `{matriz_global_id, cliente_id, locacion_id, tipo_servicio_id, vigente_desde}` → publica una versión local (crea las definiciones que falten, reutiliza las copiadas) → `{matriz_version_id, version, copiada_de_version, definiciones_creadas[]}` |
| `POST /v1/comandos/cargar_requisito_particular` | responsable_legajos | `{commitment_id, requisito_definicion_id, clasificacion, bloqueante_durante_ejecucion}` |
| `POST /v1/comandos/importar_lote_oc` | responsable_legajos | `{lote_id, origen, filas:[{clave_origen, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta, estado?, …}]}` (incremental por `clave_origen`; no cancela ausentes; idempotente por `lote_id`, sin header) |
| `POST /v1/comandos/cancelar_oc` | responsable_legajos | `{oc_id?}` o `{clave_origen?}` (uno de los dos) |

Unicidad de definición: `(nombre, categoria, tipo_sujeto_aplicable, locacion_id)` por
tenant, **incluyendo las dadas de baja** → repetir es 409 `conflicto` / `definicion_duplicada`.

### 4.4 Comandos de operación
| Ruta | Rol | Body |
|---|---|---|
| `POST /v1/comandos/cambiar_custodia` | supervisor | `{recurso_id, tipo_recurso: vehiculo\|equipo, custodio_id?, desde}` → `{custodia_id, periodo_id, periodo_cerrado_id, eventos[]}` |
| `POST /v1/comandos/corregir_custodia` | supervisor | `{periodo_id, custodio_id?, desde?, hasta?, motivo?}` |
| `POST /v1/comandos/otorgar_excepcion` | supervisor | `{referencia_evaluacion, sujeto_id, requisito_definicion_id, commitment_id, motivo, vigencia?, evidencia?}` |
| `POST /v1/comandos/revocar_excepcion` | supervisor | `{excepcion_id, motivo?}` |
| `POST /v1/comandos/registrar_constancia_del_cliente` | responsable_legajos | `{sujeto_id, requisito_definicion_id, cliente_id, evidencia, commitment_id?, emisor?, vigencia?}` → `{constancia_id, constancia_reemplazada_id, eventos[]}` |
| `POST /v1/comandos/revocar_constancia_del_cliente` | responsable_legajos | `{constancia_id, motivo?}` |
| `POST /v1/comandos/evaluar_habilitacion` | responsable_legajos | `{commitment_id, sujetos_propuestos[]}` (sin campos extra: `origen_sujetos` es 422) → decisión persistida con `referencia_evaluacion` |

Reglas que el frontend debe reflejar:
- **Custodia**: sólo el Supervisor (el responsable recibe 403). El custodio tiene que ser
  una persona activa **dentro del universo del supervisor** (403 si no); `custodio_id`
  vacío sólo para equipos (`custodio_requerido` en vehículo). El nuevo período tiene que
  empezar después del vigente (409 `conflicto`). Corregir nunca borra: el período viejo
  queda `corregido` apuntando al nuevo.
- **Excepción**: sólo sobre requisitos `excepcionable` (422 `requisito_no_excepcionable`),
  nunca sobre la empresa (422 `excepcion_de_empresa_deshabilitada`), una sola `otorgada` por
  (sujeto, requisito, compromiso) (409 `conflicto` / `excepcion_activa_duplicada`). El
  supervisor sólo ve/toca decisiones cuyos sujetos propuestos están todos en su universo
  (si no: 404 de la evaluación, 403 del sujeto).
- **Constancia del cliente**: sólo sobre requisitos `bloqueante_duro` (422
  `requisito_no_bloqueante_duro`). Registrar una nueva para la misma clave **reemplaza** a
  la vigente (`constancia_reemplazada_id` en la respuesta; la vieja queda `reemplazada`).
  General (`commitment_id` nulo) y específica (con `commitment_id`) son claves distintas:
  no se reemplazan entre sí.
- **Semántica concurrente de constancias (aceptada)**: si dos usuarios registran a la vez
  la "primera" constancia de la misma clave, el backend las serializa: **las dos pueden
  responder 200**, pero la segunda reemplaza a la primera y **sólo una queda vigente**. El
  frontend no debe asumir que un 200 significa "sigue vigente": releé el legajo (o mirá
  `constancia_reemplazada_id` de la otra respuesta). Para excepciones no hay reemplazo:
  la segunda concurrente recibe 409.
- **Evaluar habilitación** es modo decisión (persiste). El supervisor sólo consulta
  (`GET /v1/consultas/cobertura_oc`, no persiste). `evaluar_habilitacion` por el supervisor → 403.

### 4.4 bis Alertas de vencimiento (flujo 3.4)
| Ruta | Rol | Body / query |
|---|---|---|
| `POST /v1/comandos/configurar_alertas` | configuracion | `{plazo_aviso_dias (30), escalamiento_dias (7), rol_escalamiento (responsable_legajos\|supervisor\|configuracion), reconocimiento_dias (3)}` |
| `POST /v1/comandos/reconocer_alerta` | supervisor, responsable_legajos (alerta dentro de su alcance; si no, 404) | `{alerta_id, comentario?}` → silencia notificaciones `reconocimiento_dias`; **no cierra el ciclo** |
| `GET /v1/consultas/alertas_abiertas` | todos (alcance por rol) | `sujeto_id?`, `etapa?` (aviso\|recordatorio\|vencido\|escalado), paginado → `{items[], total, por_etapa{}, hoy}` |
| `GET /v1/consultas/historial_alertas` | configuracion, responsable_legajos, supervisor | `sujeto_id?`, paginado; incluye resueltas con `resuelta_motivo` (`verificacion` / `fuente_reemplazada_o_anulada`) y `eventos[]` |
| `GET /v1/consultas/configuracion_alertas` | configuracion, responsable_legajos, supervisor | → parámetros + `plazos_por_requisito[]` |

Semántica que la UI debe reflejar: `etapa` avanza sola con el tiempo (T−plazo aviso,
T−plazo/2 recordatorio, T+1 vencido, T+N escalado) y `estado` refleja la acción humana
(`abierta`, `pausada_por_accion`, `resuelta`). Cargar/proponer un documento o registrar
una excepción pausa los recordatorios; sólo un documento **verificado** que cubra el
requisito resuelve; sobre `vencido` una excepción marca `bajo_excepcion` sin resolver.
Las notificaciones salen agrupadas por destinatario (un mensaje con varias alertas). El
override de plazo por tipo de requisito se fija en `definicion_requisito.plazo_aviso_dias`
(vía alta/edición de la definición; hoy sólo por base — pendiente comando propio).

### 4.5 Consultas (`GET /v1/consultas/…`)
Paginadas: `?offset=0&limit=50` (máx. 500) → `{items[], total, offset, limit}`.

| Ruta | Roles | Query |
|---|---|---|
| `GET /v1/consultas/legajo` | todos (técnico: sólo el propio; supervisor: su universo) | `sujeto_id` |
| `GET /v1/consultas/propuestas_pendientes` | responsable_legajos | paginado |
| `GET /v1/consultas/tablero_vencimientos` | responsable_legajos, supervisor | `dias`, paginado |
| `GET /v1/consultas/backlog_oc` | responsable_legajos, supervisor | `estado?`, paginado |
| `GET /v1/consultas/cobertura_oc` | responsable_legajos, supervisor | `commitment_id` (modo consulta, no persiste) |
| `GET /v1/consultas/decisiones_oc` | responsable_legajos, supervisor | `commitment_id`, paginado |
| `GET /v1/consultas/decision` | responsable_legajos, supervisor | `referencia_evaluacion` |
| `GET /v1/consultas/historial_supervision` | configuracion, responsable_legajos | `sujeto_id`, paginado |
| `GET /v1/consultas/log_auditoria` | configuracion, responsable_legajos | `tipo?`, `desde?`, `hasta?`, paginado |
| `GET /v1/consultas/matriz_vigente` | todos | `cliente_id`, `locacion_id`, `tipo_servicio_id`, `fecha?` |
| `GET /v1/consultas/incumplimiento_empresa` | todos | — |
| `GET /v1/consultas/mi_legajo` | tecnico | — → `{persona: <legajo>, recursos_bajo_custodia: [{tipo_recurso, periodo_id, custodia_desde, ...legajo}], resumen}` (H-05: la vista compuesta del técnico) |
| `GET /v1/consultas/plantillas_globales` | configuracion, responsable_legajos | — → `{definiciones[], matrices[]}`; cada plantilla con `estado` (`sin_copia` / `al_dia` / `actualizacion_disponible`), sus líneas y `copias_locales[]` con las líneas locales, para decidir a mano qué traer |

**Plantillas globales**: la plataforma mantiene el catálogo de industria (`plataforma.*`);
el tenant copia opt-in. Cuando la plataforma sube la versión de una plantilla copiada, el
worker emite `PlantillaGlobalActualizada` una vez y encola una notificación al
responsable; nada se actualiza solo. El frontend debe mostrar la comparación (plantilla
nueva vs. copia local) desde `plantillas_globales` y ofrecer `copiar_matriz_global` /
`copiar_definicion_global`.

### 4.6 Catálogos para operar los comandos sin tipear ids (H-06)
Todos paginados (`offset/limit`, máx. 500) → `{items[], total, offset, limit}`; el alcance
del supervisor/técnico se aplica siempre (un filtro nunca amplía lo visible); otro tenant no
ve nada.

| Ruta | Roles | Query | Alimenta a |
|---|---|---|---|
| `GET /v1/consultas/sujetos` | todos (alcance) | `q` (sujeto_id / identificador), `tipo_sujeto`, `activos` (true por defecto; false = dados de baja) | alta/baja, cargar/proponer documento, custodia, excepción, constancia, asignar supervisor |
| `GET /v1/consultas/definiciones_requisito` | todos | `q`, `categoria`, `tipo_sujeto_aplicable`, `activas` | cargar documento, líneas de matriz, requisito particular, excepción, constancia |
| `GET /v1/consultas/matrices` | configuracion, responsable_legajos, supervisor | `cliente_id`, `solo_vigentes` | publicar versión (claves existentes), matriz_vigente |
| `GET /v1/consultas/usuarios` | configuracion, responsable_legajos | `q` (email/nombre), `rol`, `activos` (sin hashes) | asignar/reasignar supervisor |
| `GET /v1/consultas/documentos` | todos (alcance) | `sujeto_id`, `estado_version` (vigente por defecto; `todas`), `estado_confirmacion`, `archivo_estado` | confirmar/rechazar, preparar/confirmar subida, descarga |
| `GET /v1/consultas/excepciones` | configuracion, responsable_legajos, supervisor (alcance) | `sujeto_id`, `estado` (otorgada por defecto), `commitment_id` | revocar excepción |
| `GET /v1/consultas/constancias` | configuracion, responsable_legajos, supervisor (alcance) | `sujeto_id`, `estado` (vigente por defecto), `cliente_id` | revocar constancia |
| `GET /v1/consultas/custodias` | todos (alcance por recurso) | `recurso_id`, `custodio_id`, `solo_vigentes` | corregir custodia, cambiar custodia |
| `GET /v1/consultas/lotes` | configuracion, responsable_legajos | `estado`, `entidad` | revertir lote |
| `GET /v1/consultas/asignaciones_supervisor` | configuracion, responsable_legajos, supervisor (alcance) | `supervisor_usuario_id`, `sujeto_id`, `solo_vigentes` | reasignar supervisor |

Ya existentes que también dan ids: `backlog_oc` (commitment_id / oc_id), `decisiones_oc` y
`decision` (referencia_evaluacion), `propuestas_pendientes` (documento_id), `alertas_abiertas`
(alerta_id), `plantillas_globales` (ids globales).

**Alcance del técnico (H-05)**: se ve a sí mismo y a los vehículos/equipos bajo su custodia
vigente (legajo, documentos, custodias, sujetos); nunca a otra persona. `mi_legajo` arma la
vista compuesta persona + recursos.

Visibilidad del supervisor (regla A-04): una decisión es visible sólo si **todos** sus
sujetos propuestos están en su universo; si uno no lo está, la decisión "no existe" (404).

## 5. Storage
- `GET /v1/storage/documentos/{documento_id}/url` — URL firmada de descarga (efímera; no persistirla).
- `PUT /v1/storage/{firma}` — subida con URL firmada (sin JWT; `Content-Type` y tamaño verificados; si va un Bearer, su tenant debe coincidir).
- `GET /v1/storage/{firma}` — descarga con URL firmada.

## 6. Fechas, zonas y tipos
- Fechas de negocio (`vigente_desde`, `desde`, `vigencia`, …): `YYYY-MM-DD`. Vencimientos
  inclusivos: un documento con `vigente_hasta = hoy` está vigente hoy.
- Timestamps: ISO 8601 con zona (UTC). "Hoy" lo calcula el backend en la zona del tenant.
- UUIDs como strings; `sujeto_id`/`commitment_id` son strings de negocio (no UUID).

## 7. Códigos de error estables (`error.codigo`)
Genéricos: `validacion` (422), `no_autenticado` (401), `prohibido` (403), `no_encontrado`
(404), `conflicto` (409), `conflicto_concurrencia` (409), `regla_de_dominio` (422),
`error_interno` (500), `password_demasiado_larga` (422).

Idempotencia: `clave_idempotencia_reutilizada`, `operacion_en_proceso`, `lote_contenido_distinto` (409).

Dominio (422 salvo indicación): `requisito_no_excepcionable`, `excepcion_de_empresa_deshabilitada`,
`requisito_no_bloqueante_duro`, `sin_matriz_vigente`, `sin_sujetos_propuestos`, `sujetos_duplicados`,
`sujetos_inactivos`, `empresa_no_se_propone`, `conflicto_con_dato_verificado` (409),
`recurso_no_custodiable`, `custodio_no_permitido`, `custodio_requerido`, `legajo_dado_de_baja`,
`excepcion_activa_duplicada` (409), `constancia_activa_duplicada` (409),
`custodia_vigente_duplicada` (409), `definicion_duplicada` (409), `sin_archivo`,
`archivo_ausente`, `archivo_vacio`, `archivo_demasiado_grande`.

## 8. Lo que el frontend NO tiene todavía (deudas conocidas del backend v1)
- No hay endpoints de gestión de usuarios (alta, desactivación, cambio ni restablecimiento
  de contraseña): tenant y usuarios se administran con `scripts/administracion.py`
  (crear-tenant, crear-usuario, desactivar-usuario, listar-usuarios). Un usuario
  desactivado no puede hacer login ni refresh; su access token vigente expira solo.
- Notificaciones: sin canal externo (quedan en el log del worker). Colas `evidencia_qr`,
  `score_documental`, `validacion_evidencia`: **futuras** — ningún flujo de v1 las
  produce (verificado por test); no existe capacidad de QR, score ni validación automática.
- Publicación a Módulo 2: `PublicadorEnLog` (transporte real pendiente).
- Storage: sólo backend local (`STORAGE_BACKEND=local`); el contrato ya es el de un bucket.
