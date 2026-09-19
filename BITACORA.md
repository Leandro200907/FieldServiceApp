# Bitácora de implementación — Módulo 1

Registro cronológico de qué se hizo, qué se encontró y qué sigue. Se actualiza en cada
paso. La documentación de diseño vive en `Escritorio/Ticketera/modulo1-*.md`; esto es
solo la bitácora del código.

## 2026-09-18 — Sesión 2 (retoma desde el zip)

### Entorno
- Código extraído de `Escritorio/Ticketera/modulo1-app.zip` a `Apps/Designer/modulo1-app/`.
- `git init` + commit inicial `1ccc316` con el contenido tal cual llegó.
- `.venv` con Python 3.13.5, dependencias de `requirements.txt` instaladas.
- PostgreSQL 16.15 nativo en Windows (Docker Desktop no levantaba el motor WSL;
  winget/curl contra EDB daban 403 de CloudFront — el usuario instaló a mano).
- Base `modulo1` + roles `modulo1_owner` (owner de tablas) y `modulo1_app` (NOBYPASSRLS).
  Passwords locales de desarrollo: `changeme` (las de `.env.example`). Superusuario
  `postgres`/`postgres`, solo local.

### Validaciones
- `pytest tests/test_casos_de_oro.py` → **5 passed**.
- `alembic upgrade head` → aplica limpio al primer intento.
- Inspección del schema real: 20 tablas `modulo1.*` con RLS ENABLE+FORCE y 1 policy
  cada una; `plataforma.definicion_requisito_global` sin RLS; CHECK
  `ck_excepcion_nunca_verde` presente; índices únicos parciales
  `uq_documento_vigente` y `uq_periodo_custodia_vigente`; `modulo1_app` con
  SELECT/INSERT/UPDATE/DELETE en `modulo1` y solo SELECT en `plataforma`; ningún rol
  con BYPASSRLS ni superuser.
- Smoke test de aislamiento vía `tenant_session`: cada tenant ve solo su fila, sin
  tenant la policy rechaza, INSERT con tenant ajeno rechazado.

### Bug encontrado y corregido
- `app/db.py::tenant_session` hacía `SET LOCAL app.current_tenant = :tenant_id` con
  parámetro bind. Postgres no admite `$1` en `SET LOCAL` (psycopg3 usa parámetros
  server-side) → `SyntaxError`. Reemplazado por
  `SELECT set_config('app.current_tenant', :tenant_id, true)`, que es exactamente
  SET LOCAL (is_local=true) y sí admite bind. La decisión de arquitectura (SET LOCAL,
  nunca SET) se mantiene intacta.

### Siguiente
- Paso 4: piezas paralelizables (comandos, consultas, worker, auth) con subagentes.

### Cimientos compartidos (commit `61b5408`)
- Migración `0002`: `usuario` (JWT propio, roles múltiples, `sujeto_id` vinculado),
  `refresh_token` (hash, revocable), `asignacion_supervisor` (pieza del modelo de dominio
  que 0001 no traía; una vigente por sujeto), `tenant.slug` + función SECURITY DEFINER
  `resolver_tenant_por_slug` para login sin abrir RLS de `tenant` al rol de app.
  Aprendizaje: FORCE RLS aplica también al owner → las migraciones no pueden hacer
  UPDATE de backfill sobre tablas tenant-scoped (se usa DEFAULT en el DDL).
- `app/api/errores.py`: envelope único `{"error":{codigo,mensaje,detalles}}` + handlers.
- `app/auth/identidad.py`: `Identidad(tenant_id, usuario_id, roles, sujeto_id)` +
  `exigir_rol` (matriz 2.2 de no-funcionales).
- `app/comun/`: `eventos` (event_log síncrono + outbox solo para los 2 eventos a Módulo 2),
  `idempotencia` (Idempotency-Key en tabla), `reloj` (`hoy_del_tenant`, única forma de
  obtener "hoy"), `paginacion` (offset/limit).
- `app/main.py`: `/v1`, monta routers tolerante a módulos aún inexistentes.
- `tests/conftest.py`: fixture `tenant_de_prueba` (tenant + 4 usuarios, limpieza por RLS)
  y `cliente_api`; `token_para` firma JWT con el secreto de la app.
- `docs/BRIEF_SUBAGENTES.md`: contrato común de las 5 piezas paralelas (reglas duras,
  matriz de permisos, invariantes, catálogo de eventos, reparto de archivos disjunto,
  interfaz de orquestación).

### Piezas en paralelo (5 subagentes, en curso)
| Pieza | Archivos | Estado |
|---|---|---|
| Auth (JWT, login/refresh/logout, dependency) | `app/auth/*` | hecho (17 tests) |
| Comandos Evidencia + Requisitos | `app/modules/legajos`, `app/modules/requisitos` | hecho (16 tests) |
| Comandos Operación + orquestación del motor | `app/modules/operacion`, `app/core/orquestacion.py` | hecho (19 tests) |
| Consultas + backlog OC | `app/modules/consultas`, `app/modules/oc` | hecho (14 tests) |
| Worker + storage | `app/worker`, `app/storage` | hecho (21 tests) |

Incidente: 4 de los 5 subagentes se cortaron por límite de uso a mitad de camino; se
retomaron con su contexto intacto y terminaron. Sin pérdida de trabajo.

### Hallazgos de los subagentes que cambian cosas de los cimientos
- `resolver_tenant_por_slug` (0002, SECURITY DEFINER) no alcanzaba: FORCE RLS aplica al
  owner también y el owner no tiene BYPASSRLS. Auth lo resolvió con tabla espejo
  `tenant_slug` sin RLS sincronizada por trigger (0003_auth). Worker agregó además una
  policy `tenant_lectura_sistema` FOR SELECT TO modulo1_owner (0003_worker) para
  `listar_tenants()`. Con esa policy la función original de 0002 también funcionaría —
  posible simplificación futura, no urgente.
- `documento.sucede_a` (0003_legajos) para poder restaurar el documento anterior al
  rechazar una propuesta.
- `uq_oc_clave_origen` (0003_oc): clave estable única por tenant para carga incremental.
- Cuatro heads 0003 en paralelo → merge revision `0004_merge` escrita a mano (faltaba
  `script.py.mako` para `alembic merge`).
- `app/api/errores.py`: `jsonable_encoder` en el envelope (date/UUID en `detalles` daban 500).
- `tests/conftest.py`: hash bcrypt real de "secreto".

### Integración (commits `19eb504`, `3fd137d`)
- `app.storage.router` montado en `main.py`; `.env.example` documenta STORAGE_* y
  WORKER_POLL_SEG. 40 rutas bajo /v1.
- `tests/test_e2e_http.py`: flujo completo SOLO por HTTP (alta sujetos → definición →
  matriz v1 → documento → OC → evaluación) reproduciendo 6.1 (borde inclusive vía dos
  OCs), excepción que da `puede_asignarse_bajo_excepcion` con veredicto no verde, 6.3
  (409 en el pasado, autocierre de v1 verificado por `matriz_vigente`), 6.5 (excepción
  sin efecto tras reclasificar), constancia que sí cubre bloqueante_duro, lectura del
  técnico y log de auditoría. Pasó al primer intento.
- Auditoría rápida: ningún endpoint toma tenant_id del request; ninguna sesión fuera de
  `tenant_session`/`platform_session`; SQL siempre con bind; sin `date.today()`.
- Suite final: **96 passed**. Worker `--una-vuelta` corre.

### Pendientes conocidos (no bloqueantes para seguir)
- Transporte real hacia Módulo 2 (implementar `Publicador`); handlers `evidencia_qr`,
  `score_documental`, `validacion_evidencia` son stubs; storage S3 (hoy solo local).
- `usuario.activo` no se verifica por request (token de 30 min); rate limiting en login.
- Universo del supervisor está implementado dos veces (consultas/acceso.py y
  storage/servicio.py) — unificar en un contrato común.
- Evento para `CancelarOC` no está en el catálogo (no se emite).
- Config de storage/worker vía `os.environ`, no en `app/config.py`.

## 2026-09-18 — Sesión 3: revisión funcional contra la especificación

Cierre de las decisiones ambiguas documentadas en la sesión 2. Detalle, citas y regla
definitiva de cada una en `docs/DECISIONES_DOMINIO.md`; tests de aceptación en
`tests/test_reglas_cerradas.py` (14 tests).

- **Propuesta del técnico**: la implementación coincidía con la spec (2.2). Se agregó la
  restauración por cadena `sucede_a` (antecesor no terminal más cercano) para el caso
  lote revertido + propuesta rechazada.
- **Agregación del veredicto**: cuatro diferencias corregidas en `app/core/orquestacion.py`:
  matriz vigente a `periodo_desde` (no a hoy); `bloqueante_durante_ejecucion` ahora decide
  si `vence_durante_el_trabajo` bloquea; representante por tipo elegido por asignabilidad
  antes que por severidad (un sujeto bajo excepción con efecto cubre por delante de uno
  bloqueado); sin legajo de empresa → `no_habilitado`. El veredicto global sigue siendo el
  peor de los representantes; `ck_excepcion_nunca_verde` se cumple por construcción.
- **Lotes**: revertir no pisa una carga manual posterior (coincide con la spec 2.5 +
  2.12); se implementaron las tres políticas de reimportación de modelo-dominio 2.11
  (sin cambios / renovación / conflicto con dato verificado).
- **Universo del supervisor**: unificado en `app/auth/alcance.py`; las dos versiones
  anteriores eran semánticamente iguales salvo la lista de roles que ven todo, que ahora
  es un parámetro explícito por capacidad.
- Test 6.4 de orquestación reescrito: la segunda mitad dependía de que la matriz se
  eligiera por "hoy"; ahora prueba el borde de día sobre el vencimiento de una constancia.
- Suite: **110 passed**.

## 2026-09-18 — Sesión 4: integración y robustez final

- **Bootstrap desde cero** en `modulo1_limpia` (base vacía): las 6 migraciones
  (0001 → 0002 → 4×0003 → 0004_merge) aplican limpias. Verificado: 24/25 tablas con
  RLS+FORCE (la 25ª es el espejo `tenant_slug`, sin GRANT al rol de app), 3 funciones
  SECURITY DEFINER del owner, 1 trigger, roles sin BYPASSRLS, 38 índices únicos, CHECKs.
- **Suite y E2E sobre la base limpia**: 110 passed antes de los cambios de esta sesión.
- **Bug real de concurrencia** (encontrado por análisis, confirmado con tests de hilos):
  dos versiones nuevas del mismo (sujeto, requisito) a la vez → la segunda chocaba contra
  `uq_documento_vigente` con 500. Igual para revertir-lote vs carga manual y para dos
  primeras asignaciones de supervisor. Corrección: `_bloquear_legajo` como ancla de
  serialización (orden fijo legajo → documento) + handler global `IntegrityError → 409`.
- **Código muerto**: `app/modules/consultas/acceso.py` (solo reexportaba `app.auth.alcance`
  y tenía `ve_todo_el_tenant` sin usar) eliminado.
- **Tests nuevos** (`tests/test_robustez.py`, 59): cadenas A→B→C con todas las
  combinaciones de estados (6), invariantes de agregación combinatorias (36 pares de
  perfiles + bordes de matriz + empresa sin legajo + no bloqueante en ejecución),
  aislamiento entre dos tenants por HTTP / servicios / `alcance` / storage / JWT
  manipulado, concurrencia real con hilos (5) y contrato HTTP (40 rutas, códigos,
  envelope, serialización). Fixture `dos_tenants` en conftest.
- Suite final sobre base limpia: **169 passed**. `.env` queda apuntando a
  `modulo1_limpia`; `.env.dev` conserva la base de desarrollo (ambos ignorados por git).

## 2026-09-19 — Sesiones 5–6: remediación de auditoría externa (A-01…A-07, M-01…M-04)

Orden pactado y commits (todo con migraciones lineales, un solo head, un integrador):
A-01/M-07 (roles y bootstrap sin secretos) · A-02/M-05 (universo del supervisor único,
`app/auth/alcance.py`) · A-04 (modo decisión sólo responsable; `evaluacion_sujeto_propuesto`,
0006) · A-03/A-06 (idempotencia con fingerprint inmutable + exclusión real, 0007/0009;
leases con `lease_token`, 0008) · A-05 (purga en dos fases, at-least-once físico) · A-07
(revaluación declarativa `EVENTOS_FUENTE`, outbox dedup, 0010; commit `4a98085`).

- **M-01 (`78f597e`, 0011)**: FKs compuestas `(tenant_id, id)` en 32 relaciones; UNIQUE
  `(tenant_id, id)` en 7 padres; dos CASCADE corregidos; `_sin_force_rls` para que la
  validación sea un escaneo real. `tests/apoyo.py` planta padres. 28 tests.
- **M-02 (`693a3e8`, 0012)**: índices únicos parciales de excepción/constancia activas
  (DECISIONES §11); ancla `FOR UPDATE` sobre el legajo; reemplazo antes del INSERT;
  23505 residual → 409 de dominio. 11 tests (hilos + proxy de sesión para la ventana
  residual + HTTP).
- **M-03 (`ffb7ed1`)**: validaciones de custodia (recurso/custodio existentes, activos, del
  tipo correcto, custodio en el universo del supervisor, sin custodio sólo para equipo)
  y ancla sobre el legajo del recurso (DECISIONES §12). 20 tests.
- **M-04 (`59e658e`, 0013)**: `UNIQUE NULLS NOT DISTINCT` sobre la clave completa de la
  definición de requisito; la migración aborta con diagnóstico si hay duplicados (test
  que lo prueba haciendo downgrade/upgrade real). 8 tests.
- Verificación por migración: upgrade/downgrade/upgrade en `modulo1_limpia` y `modulo1`,
  bootstrap desde cero en `modulo1_boot` (16 upgrades), head único, 0 tablas sin FORCE
  RLS. Consultas finales en las tres bases: 0 FKs sin validar, 0 FKs simples
  tenant-scoped, 0 duplicados activos (excepciones, constancias, custodias vigentes),
  0 definiciones duplicadas NULL-aware. Suite final: **343 passed**.
