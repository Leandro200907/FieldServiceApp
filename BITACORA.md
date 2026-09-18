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
| Auth (JWT, login/refresh/logout, dependency) | `app/auth/*` | en curso |
| Comandos Evidencia + Requisitos | `app/modules/legajos`, `app/modules/requisitos` | en curso |
| Comandos Operación + orquestación del motor | `app/modules/operacion`, `app/core/orquestacion.py` | en curso |
| Consultas + backlog OC | `app/modules/consultas`, `app/modules/oc` | en curso |
| Worker + storage | `app/worker`, `app/storage` | en curso |
