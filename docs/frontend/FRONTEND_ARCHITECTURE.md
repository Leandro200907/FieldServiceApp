# FieldServiceApp — Arquitectura frontend propuesta

Actualizado 21/09/2026 · Estado: continuidad de diseño/layout/estados/mocks confirmada; repo por identificar · Baseline bbf42b5

## ADR-001 · React + TypeScript + Vite

Se propone una SPA interna con backend FastAPI separado. El trabajo dominante es sesión, formularios, consultas y evidencia; no hay necesidad aprobada de SEO, renderizado servidor ni servidor frontend propio.

| Criterio del proyecto | Vite | Next.js |
|---|---|---|
| React + TypeScript y aplicación de navegador | Ajuste directo | También posible |
| API existente como único dueño del dominio | Cliente HTTP sin otra capa de aplicación | Hay que delimitar componentes servidor, cliente y cualquier capa intermedia |
| SSR/SEO requerido hoy | No requerido | Capacidades que no necesitamos en esta fase |
| Hosting | Artefactos estáticos y proxy de API | Depende de capacidades usadas; una exportación estática también es posible |
| Sesión con cookies HttpOnly/BFF | Requiere servicio/proxy de sesión adicional | Puede alojar esa capa; no la vuelve parte del contrato actual automáticamente |
| Cambio futuro | Revisar si aparece necesidad real de BFF/SSR | Preferible si se aprueba un frontend con responsabilidades servidor |

**Decisión recomendada: Vite.** Reduce decisiones de runtime para la base actual. No se considera Next.js incorrecto ni imposible en estático. La documentación de Vite confirma plantilla `react-ts` y generación de assets; Next.js describe la separación servidor/cliente. Esta elección es juicio arquitectónico para este proyecto, no un benchmark. Fuentes consultadas el 20/09/2026: [Vite](https://vite.dev/guide/), [Next.js](https://nextjs.org/docs/app/getting-started/server-and-client-components).

## Stack propuesto

| Responsabilidad | Herramienta / criterio |
|---|---|
| UI y lenguaje | React, TypeScript con `strict` y sin `any` para tapar vacíos del contrato |
| Build | Vite; versiones compatibles fijadas en lockfile al iniciar I1, sin instalar `latest` en CI |
| Rutas | React Router; tabla central de rutas y capacidades |
| Consultas | TanStack Query para caché en memoria, cancelación e invalidación; sin persistencia de datos documentales |
| HTTP/tipos | `openapi-typescript` + `openapi-fetch`; transportes de JSON y URL firmada separados |
| Formularios | React Hook Form; restricciones de forma del contrato; validación de dominio devuelta por servidor |
| Visual | CSS Modules + custom properties; componentes propios pequeños sobre HTML semántico; sin un segundo sistema de estilos |
| Mocks | MSW solo en desarrollo/test; schemas OpenAPI como límite; validación JSON Schema compatible con la versión del contrato |
| Checks | TypeScript, ESLint; Vitest/Testing Library en políticas críticas; Playwright para recorridos reales y responsive |
| Dependencias | npm + lockfile, runtime Node compatible verificado en I1; registrar versiones exactas antes del primer build |

El generador y cliente se apoyan en [openapi-typescript](https://openapi-ts.dev/introduction) y [openapi-fetch](https://openapi-ts.dev/openapi-fetch/). Los tipos no validan respuestas en runtime y no pueden recuperar campos ausentes del OpenAPI. Los demás componentes son opciones propuestas; su compatibilidad exacta se verificará al fijar versiones.

## Límites y estructura de carpetas

| Ruta propuesta | Responsabilidad |
|---|---|
| `frontend/package.json`, `package-lock.json` | Dependencias y scripts reproducibles |
| `frontend/contracts/modulo1/openapi.json` | Baseline aceptada, copiada sin editar desde backend |
| `frontend/contracts/modulo1/baseline.json` | Hash, commit declarado, fecha y delta de contrato |
| `frontend/src/app/` | Providers, router, shell, capabilities, flags y boundary de errores |
| `frontend/src/api/generated/` | Tipos regenerados; nunca edición manual |
| `frontend/src/api/transport/` | Auth headers, errores, request_id, timeout y política de replay |
| `frontend/src/api/session/` | Estado de sesión, refresh único, generación de sesión, limpieza |
| `frontend/src/api/idempotency/` | Identidad de intención y conservación de claves |
| `frontend/src/features/auth/`, `profile/` | Login, logout y `/auth/yo` |
| `frontend/src/features/legajos/`, `evidencias/`, `propuestas/` | Recorridos documentales |
| `frontend/src/features/matrices/`, `oc/`, `decisiones/` | Configuración y operación |
| `frontend/src/features/vencimientos/`, `auditoria/`, `supervision/` | Lecturas y administración autorizada |
| `frontend/src/features/documentation-planning/` | Puerto reemplazable, contratos temporales y prototipos S-09A/S-09B; no cliente HTTP ni reglas de dominio |
| `frontend/src/ui/` | Botones, campos, tablas, paneles, estados, colores y tipografía |
| `frontend/src/mocks/` | Handlers por operación y fixtures verificadas; no motor de dominio |
| `frontend/tests/contract/`, `tests/e2e/` | Checks de contrato y recorridos críticos |
| `frontend/docs/` | Plan, matriz, ADRs y gaps vivos |

`frontend/` es ubicación propuesta, no una carpeta creada en el backend. Ajustar al repo elegido en D-05. Las features no se importan mutuamente para compartir reglas; UI y transporte compartidos tienen dueño integrador. No hay motor de habilitación frontend. Ningún selector pendiente se reemplaza con un input de UUID/ID. SEL-01…SEL-33, G-16 y G-17 definen sus dependencias; propuestas de endpoint no entran en contratos ni mocks.

## ADR-002 · Contrato, tipos y base URL

Después de aprobar: generar `src/api/generated/modulo1.d.ts` desde la copia de `docs/openapi.json`; CI regenera y exige diff vacío. Rutas literales provienen de `paths`, nunca strings armados con nombres de comando libres.

Los paths ya contienen `/v1`. `baseUrl` debe ser el **origen de API sin `/v1`**, o el origen actual detrás de proxy. No copiar el ejemplo defectuoso del handoff que añade `/v1` en ambos lados. `baseUrl` prefija la URL según [la API de openapi-fetch](https://openapi-ts.dev/openapi-fetch/api).

La API extraída no configura CORS. Se propone mismo origen mediante proxy local y reverse proxy de despliegue; preserva `/v1` y permite leer `X-Request-ID`. Si se usan orígenes separados, el equipo backend/infra deberá configurar orígenes, headers y exposición de `X-Request-ID`; no se modifica backend en esta tarea. Las variables públicas de build solo contienen configuración pública, jamás JWT_SECRET, STORAGE_SECRET o claves de proveedor.

### Tipado incompleto

42 respuestas de éxito son objetos libres, 2 no tienen esquema. Generar tipos de requests y rutas sí es posible. Para respuestas de dominio, el frontend mantendrá `unknown` en el límite y dejará su integración desactivada hasta recibir schemas. No castear a interfaces manuales deducidas de SQL/handoff. G-01 documenta esta limitación; G-03 afecta binarios y firma. La opción de un contrato suplementario requeriría aprobación expresa; no se adopta en este plan.

## ADR-003 · Sesión y refresh

Recomendación D-02: access/refresh **solo en memoria por pestaña**. Recarga o cierre vuelve al login. No localStorage, sessionStorage, IndexedDB ni caché persistente de tokens o evidencia. No existe cookie HttpOnly ni BFF de sesión en el contrato actual.

1. Login envía exactamente `tenant_slug`, `email`, `password`; no trim/truncado de password. El límite de 72 bytes UTF-8 del handoff/código se trata como restricción de transporte documentada en G-11, no como nueva regla de dominio. Errores genéricos no revelan si existe tenant/email.
2. Guardar el par en memoria; consultar `/v1/auth/yo` antes de habilitar rutas. Perfil solo muestra tenant_id, usuario_id, roles y sujeto_id. No inventar nombre, avatar personal, email, zona horaria o edición de perfil.
3. Calcular un plazo preventivo con `expires_in`; margen pequeño configurable, sin asumir TTL fijo. Un solo refresh en vuelo por sesión/pestaña; las demás solicitudes esperan esa promesa. Reemplazar el par de manera atómica. Releer `/v1/auth/yo` con el token nuevo antes de reanudar la UI protegida; actualizar roles/sujeto y eliminar caché afectada si cambia la identidad autorizada. Esta lectura interna no debe esperar la misma promesa de refresh, para evitar un bloqueo circular.
4. 401 con token que el cliente aún considera vigente: invalidar sesión, siguiendo el handoff de desactivación inmediata. No probar refresh en bucle. 401 tras expiración conocida: un refresh y como máximo un replay de lectura; comandos solo con política idempotente y la misma intención. Si la petición llevaba una generación anterior del token, verificar primero si otro refresh ya produjo una nueva, sin iniciar otro refresh.
5. 401 en login/refresh: terminar intento/sesión. Refresh con resultado de red incierto: no reenviar el token consumible ciegamente; volver a autenticar. G-11: esos 401 no están declarados en OpenAPI; manejarlos como estado HTTP de transporte y pedir corrección del contrato.
6. Logout llama a `/v1/auth/logout` con el refresh vigente y Bearer, si sigue disponible. Incrementar generación de sesión, abortar requests, vaciar caché y revocar object URLs siempre, incluso ante error. Una respuesta tardía de refresh nunca puede restaurar la sesión. Si no se confirma revocación remota, informar «Sesión cerrada en este dispositivo; no se pudo confirmar la revocación».
7. Cache keys incluyen tenant_id, usuario_id y contexto de permiso; se eliminan al cambiar de identidad/roles. No se permiten datos de usuario previo durante el siguiente login.

Un usuario multirrol usa sus permisos reales; elegir un contexto cambia el menú, nunca cambia el token ni crea otro rol. Roles desconocidos se ignoran con acceso denegado por defecto. `/auth/yo` refleja claims actuales: solo el estado activo se consulta en DB por request. No prometer aplicación inmediata de cambios de rol que no tenga el backend. Ante cambios de acceso observados, invalidar/refrescar perfil o exigir login; 403 nunca causa refresh infinito.

## Errores, request_id y concurrencia

Consumir `ErrorEnvelope.error`: `codigo`, `mensaje`, `detalles`, `request_id`. Renderizar texto escapado; no HTML de servidor. El esquema define `detalles` con objetos/listas/null sin estructura completa de cada detalle; comprobar su forma antes de asociar `loc` con un input.

| Resultado | Comportamiento UI |
|---|---|
| 401 | Política de sesión anterior; conservar destino interno validado, no un redirect externo |
| 403 | «No tenés permiso para esta acción»; eliminar datos invalidados, no sugerir acceso cambiando IDs |
| 404 | Recurso no disponible; no confirmar que existe fuera del alcance |
| 409 en proceso | Mostrar pendiente; reintento explícito acotado con misma clave/body |
| 409 clave reutilizada | Detener; no generar otra clave automáticamente para el mismo envío |
| 409 concurrencia | Releer estado, conservar formulario, pedir revisión antes de un nuevo intento |
| 422 | Errores por campo si hay ubicación válida y mensaje global; sin esconder rechazo de dominio |
| 500/503 | Mensaje claro, referencia de solicitud y reintento de lectura; no afirmar fracaso definitivo de una mutación |
| Red/timeout/respuesta no JSON | Error de transporte distinto del ErrorEnvelope; mutación de resultado incierto, no «guardado» |

Generar `X-Request-ID` por intento HTTP; mostrar preferentemente `error.request_id` y luego header. Si ninguno llegó, señalar que solo existe referencia local, sin atribuirla al servidor. Acción «Copiar referencia» copia solo ID y contexto mínimo, nunca token/body/URL firmada. No colocar el request_id como ID de evento de auditoría.

En un 200 no aplicar resultados optimistas de dominio: invalidar y reconsultar lecturas afectadas. Dos constancias pueden devolver 200 y la segunda reemplazar la primera; una confirmación HTTP no prueba vigencia actual. El frontend tampoco resucita una propuesta o calcula su sucesión.

## Idempotency-Key

Crear con `crypto.randomUUID()` una clave por intención de comando, y reutilizarla para reintentos de esa misma operación con body inmutable. Deshabilitar doble click, pero sin depender de ello para idempotencia. Nueva intención o cambio confirmado de payload → nueva clave; refresh no cambia la clave. Guardar el registro solo en memoria; una recarga con resultado incierto requiere reconsultar, no reenviar automáticamente.

Enviar el header solamente en operaciones que lo declaran. `importar_lote` e `importar_lote_oc` tienen idempotencia basada en `lote_id`; el primero además expone header, pero la identidad del lote manda. El de OC no declara el header. Mismo lote nunca cambia contenido silenciosamente. Auth y storage firmado no heredan esa garantía.

Preparar subida y confirmar subida son **dos comandos y dos claves**. Al vencer la URL de preparación, solicitar una intención nueva de preparación, porque repetir la clave original puede devolver la URL ya vencida. El PUT transmite bytes crudos con Content-Type acordado; no se repite como JSON ni se le añade Idempotency-Key de comandos.

## Evidencia

Flujo diseñado, pendiente G-01/G-03: cargar documento/proponer → obtener documento_id real → preparar → PUT de archivo crudo → confirmar → reconsultar legajo/propuestas. El archivo binario y el estado de confirmación documental son cosas distintas. La propuesta técnica no se convierte en verificada por completar el upload.

Transportador de URLs firmadas separado, sin Authorization por defecto; host/esquema permitidos por configuración, HTTPS en producción. No modificar ni reconstruir la firma. No persistir URL, no loguearla, no mandarla en telemetría/referrer. Descargar solicita URL nueva por acción; revocar blob URLs al cerrar. Un 401/403 del storage firmado no dispara refresh de auth automáticamente.

Tamaño y Content-Type provienen de preparación; G-03 obliga a tiparlos primero. Un PUT fallido conserva documento_id e intención de carga; no repetir crear documento para recuperarse. Una propuesta ya creada puede afectar el veredicto antes de completar el binario: avisar antes del envío y mostrar claramente «Archivo pendiente» si falla. El servidor decide el efecto sobre el dominio.

## Mocks y flags

MSW en entorno explícito de desarrollo; modo real falla ante endpoint desconocido. Fixtures sintéticas de auth pueden derivarse de schemas; `roles` es `string[]`, no un enum de permisos, por lo que el conjunto de roles conocidos sale de las especificaciones y queda registrado. Las respuestas objeto libre solo permiten pruebas del límite, por ejemplo «respuesta sin estructura utilizable». No usar `{items:[], total:0}` como mock de negocio si esos campos no están publicados.

Los wireframes son **diseños sin datos**, separados de handlers HTTP. Los casos 401 de login/refresh y transferencia binaria son conflictos de contrato; pueden probarse a nivel transporte pero no venderse como mocks conformes al OpenAPI original.

Excepción controlada para S-09A/S-09B: se admiten ejemplos de dominio dentro de un adaptador local `DocumentationPlanningAccess`, identificados como `temporary-contract-mock` y rotulados en la propia pantalla. Su objetivo es validar jerarquía, estados y explicación; no derivan del OpenAPI auditado, no interceptan HTTP y no se importan desde `src/api`. Las tres operaciones propuestas permanecen únicamente en API_GAPS §8 hasta recibir `docs/PROYECCION_DOCUMENTAL.md` y un OpenAPI actualizado. Reemplazar el adaptador es obligatorio antes de habilitar integración.

Flags propuestos de UI: `drive`, `notifications`, `documentPackageQr`, `documentScore`, `legajoExport`, `alertConfiguration`, `alertLifecycle`, `globalTemplates`, `module2Integration`, `documentBatchImport`, `typedBusinessViews`, `signedEvidence`, `technicianCompositeView`, `documentationCalendarIntegration`, `backlogDocumentationIntegration`. Todos los flags de integración permanecen inactivos. Los prototipos S-09A/S-09B pueden renderizarse con su marca temporal sin encenderlos. Ninguno se enciende por detectar un número de versión o una cola existente. Sin endpoint de capacidades, usar manifiesto de release revisado junto al contrato, no sondas sobre rutas inventadas.

## Sistema visual y responsive

Propuesta sobria de operación: fondo `#F4F6F8`, superficies blancas, texto `#172B3A`, acción principal `#145C56`, bordes `#C9D3DB`; advertencia ámbar, error rojo y pendiente gris. Tipografía del sistema; escala 12/14/16/20/28 px, espaciado 4/8/12/16/24/32 px, radios 8 px. Objetivos táctiles 44 px; foco visible; pruebas de contraste antes de aprobar componentes.

Desktop: sidebar de 240 px, encabezado con contexto y sesión, contenido con título/estado/acción. Tablet: navegación plegable y columnas adaptables. Móvil: barra superior, drawer de menú, tarjetas con etiquetas o tabla desplazable cuando comparar columnas sea esencial; filtros en panel. No bottom bar que oculte funciones de un rol multicapacidad.

Estados reutilizables: carga, vacío real, falta de permiso, no disponible, error con referencia, conflicto, resultado incierto y actualización pendiente. «Pendiente backend» es una anotación del catálogo de diseño; no una falsa pantalla operativa. Separar cumplimiento, resultado de decisión y cobertura en UI; una excepción no vuelve verde el cumplimiento. No inferir que la falta de datos implica cero incumplimientos. Técnico: panel compuesto bloqueado hasta G-16. Supervisor: Mi legajo personal y Equipo supervisado son contextos separados hasta G-17; el rol nunca se convierte en un veredicto documental. Sin seleccionar otra persona/recurso, sin elegir el primer vehículo ni calcular custodia vigente en el navegador.
