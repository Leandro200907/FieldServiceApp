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
