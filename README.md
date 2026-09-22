# Módulo 1 — Documentación habilitante (backend)

Backend del Módulo 1 del FSM (habilitación documental de personas, vehículos, equipos y
empresa para compromisos/OC en Vaca Muerta). Implementa el alcance v1 de los documentos de diseño
del Project (`modulo1-documentacion-habilitante.md`, `modulo1-modelo-dominio.md`,
`modulo1-especificacion.md`, `modulo1-no-funcionales.md`, `modulo1-arquitectura-tecnica.md`,
`modulo1-wireframes-api.md`). Las decisiones que esos documentos dejaron abiertas están
cerradas en [docs/DECISIONES_DOMINIO.md](docs/DECISIONES_DOMINIO.md); el contrato para
el frontend en [docs/HANDOFF_FRONTEND.md](docs/HANDOFF_FRONTEND.md); el diario de
sesiones en [BITACORA.md](BITACORA.md).

## Cifras (verificadas por `tests/test_docs_actualizados.py`)

- **Rutas HTTP:** 85 operaciones sobre 84 paths bajo `/v1` (OpenAPI en `/docs`).
- **Migraciones:** 24 archivos en `migrations/versions/`, un solo head: `0021_validacion_evidencia`.
- **Tests:** 533 (pytest, contra PostgreSQL real; incluyen los 5 casos de oro, E2E HTTP,
  concurrencia con hilos, aislamiento multi-tenant y dos workers).
- Esquema documentado: [docs_schema_actual.sql](docs_schema_actual.sql) (generado, no editar).
- Contrato HTTP versionado: [docs/openapi.json](docs/openapi.json) (generado por
  `scripts/generar_openapi.py`; `tests/test_openapi_versionado.py` lo compara con la app).

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2.0 Core (`text()` + bind params, sin ORM) · Alembic ·
PostgreSQL 16 (RLS por tenant, `FORCE ROW LEVEL SECURITY`) · psycopg 3 · PyJWT · bcrypt ·
pytest. Sin librería de cola: cola nativa en Postgres (`FOR UPDATE SKIP LOCKED` + leases).

## Estructura

```
app/
  main.py               # FastAPI, monta routers bajo /v1; handlers de error + request_id
  version.py            # VERSION y MIGRACION_HEAD (readiness y docs lo verifican)
  config.py / entorno.py # settings desde entorno (precedencia proceso > ENV_FILE > .env); nunca secretos en código
  db.py                 # engine (rol app), tenant_session (SET LOCAL app.current_tenant)
  api/errores.py        # envelope de error único, X-Request-ID, 500 con stack trace en log
  api/salud.py          # /salud/vivo (liveness) y /salud/listo (readiness)
  auth/                 # JWT, login/refresh/logout, passwords (bcrypt, límite en bytes),
                        # identidad y roles, alcance (universo del supervisor)
  core/                 # motor puro de evaluación + orquestación (decidir/consultar),
                        # revaluación declarativa, incumplimiento de empresa, etapa de alerta (pura)
  comun/                # eventos + outbox, idempotencia, reloj del tenant, paginación
  modules/
    legajos/            # sujetos, documentos, acreditaciones, inducciones, lotes, supervisor
    requisitos/         # definiciones, matrices, requisitos particulares
    operacion/          # custodia, excepciones, constancias, evaluar habilitación
    alertas/            # alerta de vencimiento (agregado, políticas, coalescing, consultas)
    notificaciones/     # canales mail / Telegram (adaptadores), entrega idempotente, render
    paquete/            # paquete de entrega público firmado + QR (sin JWT, rate limit)
    score/              # score de salud documental + snapshot diario
    exportacion/        # exportar legajo (json/csv) con traza
    drive/              # carpeta de Drive de solo lectura: proveedor, escaneo, extracción por confianza, bandeja
    oc/                 # importación/cancelación de OC (vista de compromiso)
    consultas/          # GET /consultas/* (read models con alcance por rol) + catálogos para operar sin ids (H-06) + mi_legajo (H-05)
  storage/              # contrato de storage, backend local firmado, subida/descarga
  worker/               # cola con leases, outbox, procesos de reloj, dead-letter
migrations/             # Alembic (0001 … 0021, lineales, un head)
scripts/                # crear_roles.sql, crear_base.sql, administracion.py, precargar_plantillas.py, generar_schema.py, generar_openapi.py
tests/                  # suite completa (ver Cifras)
docs/                   # DECISIONES_DOMINIO.md, HANDOFF_FRONTEND.md, BRIEF_SUBAGENTES.md
```

## Bootstrap desde cero (local)

Requiere PostgreSQL 16 con un superusuario y `psql`/`pg_dump` en el PATH (o rutas absolutas).

```bash
# 1) Roles (contraseñas SOLO por variables de psql, mínimo 12 caracteres; nunca en el repo)
psql -U postgres -h localhost -v ON_ERROR_STOP=1 -v owner_password='…' -v app_password='…' -f scripts/crear_roles.sql
```

```bash
# 2) Base con owner correcto
psql -U postgres -h localhost -v ON_ERROR_STOP=1 -v db=modulo1 -f scripts/crear_base.sql
```

```bash
# 3) Entorno virtual + dependencias fijadas por hash
python -m venv .venv && .venv/Scripts/python -m pip install --require-hashes -r requirements.lock -r requirements-dev.lock
```

```bash
# 4) Configuración (copiar y completar; DATABASE_URL_MIGRATIONS solo la usa Alembic)
cp .env.example .env
```

```bash
# 5) Migraciones (rol owner, vía DATABASE_URL_MIGRATIONS del ENV_FILE)
ENV_FILE=.env .venv/Scripts/alembic upgrade head
```

```bash
# 6) Catálogo global de industria (plantillas de definiciones y matrices por operadora; rol owner; idempotente)
ENV_FILE=.env .venv/Scripts/python scripts/precargar_plantillas.py docs/plantillas/base_v1.json
```

El contenido de `docs/plantillas/base_v1.json` es una **precarga base a validar con cada
operadora** antes de un piloto (no la matriz oficial). Al subir `version` de una plantilla
y volver a correr el script, el reloj del worker (`control_plantillas`) emite
`PlantillaGlobalActualizada` una vez por tenant con copia local y encola la notificación
al responsable; la copia nunca se actualiza sola (`GET /v1/consultas/plantillas_globales`
muestra plantilla y copia lado a lado; `copiar_matriz_global` publica una versión nueva).

## Administración inicial (CLI, sin endpoints ni pantallas en v1)

`scripts/administracion.py` corre con `DATABASE_URL` del archivo de entorno (rol de
aplicación, respeta RLS). La contraseña entra por la variable `USUARIO_PASSWORD` o, si no
está, por prompt seguro (`getpass`, dos veces, sin eco); **nunca** por argv ni stdout.
Máximo 72 bytes UTF-8, sin truncar.

```bash
# 1) tenant (imprime el tenant_id)
.venv/Scripts/python scripts/administracion.py crear-tenant --slug acme --nombre "ACME SRL"
```

```bash
# 2) primer responsable de legajos (+ configuración para cargar definiciones y matrices)
.venv/Scripts/python scripts/administracion.py crear-usuario --tenant-slug acme --email ana@acme.test --nombre Ana --rol responsable_legajos --rol configuracion
```

```bash
# 3) supervisor
.venv/Scripts/python scripts/administracion.py crear-usuario --tenant-slug acme --email sup@acme.test --nombre Sup --rol supervisor
```

```bash
# 4) desactivar un usuario: efectivo de inmediato (cada request protegido comprueba `activo` en la base; login y refresh 401; refresh tokens revocados)
.venv/Scripts/python scripts/administracion.py desactivar-usuario --tenant-slug acme --email sup@acme.test
```

```bash
.venv/Scripts/python scripts/administracion.py listar-usuarios --tenant-slug acme
```

Pendiente expresamente para después de v1: cambio y restablecimiento de contraseña,
reactivación (exigirá `tokens_validos_desde` o una versión de seguridad en el claim para
que no revivan tokens emitidos antes de la desactivación) y gestión de usuarios por API.

## Correr

```bash
# API
.venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
# Worker (polling cada WORKER_POLL_SEG; --una-vuelta para cron/CLI). Se pueden correr varias instancias.
.venv/Scripts/python -m app.worker.main
```

```bash
# Tests (usan DATABASE_URL de .env; la base debe estar en el head)
.venv/Scripts/python -m pytest -q
```

Salud (públicas, sin JWT): `GET /v1/salud/vivo` (liveness) y `GET /v1/salud/listo`
(readiness: DB, migración en `MIGRACION_HEAD`, storage y worker — último latido global en
`latido_proceso` más reciente que `WORKER_LATIDO_MAX_SEG`, 120 s por defecto; estados
`ok`/`sin_latido`/`vencido`/`no_disponible`). 503 si algo falla, sólo estados cerrados,
sin DSN, rutas, hostname, PID ni excepciones.

## Archivo de entorno (`ENV_FILE`)

Regla única para API, worker, Alembic y scripts (`app/entorno.py`), de mayor a menor precedencia:

1. **variables reales del proceso** (siempre ganan);
2. el archivo indicado por **`ENV_FILE`**, si la variable está definida (sólo ése; si no existe, valen únicamente las del proceso);
3. **`.env`** del directorio de trabajo, únicamente cuando `ENV_FILE` no fue indicado.

API y worker registran al arrancar el archivo elegido, la base y el host (nunca secretos ni
el DSN completo). `tests/test_env_file.py` arranca API y worker con dos archivos distintos y
comprueba que cada uno usa el suyo.

## Dependencias reproducibles (M-08)

- `requirements.in`: dependencias directas de producción. `requirements-dev.in`: tests y
  tooling (constreñido por `requirements.lock`).
- `requirements.lock` / `requirements-dev.lock`: versiones exactas **con hashes**; la
  instalación es `pip install --require-hashes -r requirements.lock [-r requirements-dev.lock]`.
- Regenerar (después de tocar un `.in`):

```bash
.venv/Scripts/pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements.lock requirements.in
```

```bash
.venv/Scripts/pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.lock requirements-dev.in
```

`.venv/` no se versiona (`.gitignore`).

## Migraciones

- Un único integrador toca Alembic; migraciones temáticas, lineales, un solo head
  (`alembic heads`). Cada una se verifica con upgrade → downgrade → upgrade y bootstrap desde cero.
- `app/version.py::MIGRACION_HEAD` debe apuntar al head: readiness lo compara con la base y
  `tests/test_docs_actualizados.py` lo compara con `migrations/`, el README y el dump.
- Regenerar el esquema documentado (base creada desde cero, sin datos ni propietarios):

```bash
ENV_FILE=.env.boot .venv/Scripts/python scripts/generar_schema.py
```

## Operación y diagnóstico

- Toda respuesta lleva `X-Request-ID` (se respeta el entrante). Un 500 se registra con
  stack trace y `request_id`; el cliente recibe sólo `error_interno` + `request_id`. Nunca se
  registran headers, cuerpos, tokens ni contraseñas; los 422 no devuelven el `input`.
- Worker: leases con token (fencing), backoff exponencial (30 s · 2ⁿ⁻¹, tope 1 h), 5
  intentos, dead-letter (`job_queue.estado='fallido'` con `ultimo_error` saneado y
  `fallido_en`). Latidos en `latido_proceso` (el global alimenta readiness).
- Colas **futuras** (`evidencia_qr`): ningún
  flujo soportado en v1 las produce — `tests/test_colas_futuras.py` lo verifica por
  relevamiento del código y corriendo el E2E principal + una vuelta del worker con cero
  jobs en dead-letter. Si aparece un productor, ese test falla hasta implementar el handler
  o desactivar el productor. Notificaciones: mail/Telegram según `configuracion_canales`
  del tenant y las variables de plataforma (`SMTP_*`, `TELEGRAM_BOT_TOKEN`); sin canal
  habilitado quedan en el log con traza `notificacion_envio`.
- Purga de archivos: dos fases (`purga_pendiente` confirmado → borrado físico fuera de tx →
  `purgado`); borrado físico al menos una vez, confirmación exactamente una vez.

## Estado

| Pieza | Estado |
|---|---|
| Esquema + RLS + FKs compuestas por tenant, unicidades activas y NULL-aware | Hecho (0001–0016) |
| Catálogo y matrices globales de industria, copia opt-in, aviso de versión nueva (no-funcionales 1.5) | Hecho (0016) |
| Alerta de vencimiento completa: aviso/recordatorio/vencido/escalado, pausa, resolución por verificación, reconocimiento, rol de escalamiento y plazos configurables, coalescing, tablero e historial, OC sin matriz | Hecho (0017) |
| Notificaciones reales por mail (SMTP) y Telegram (bot), configuración por tenant, vinculación de chat, entrega at-least-once con traza por destinatario (`sin_canal`/`registrado_log` propios, nunca pérdida silenciosa ni "log" contado como entrega real) | Hecho (0018/0019); WhatsApp diseñado, no activo |
| Paquete de entrega con link público firmado + QR por entidad (vencimiento, revocación, rate limit, traza de accesos) | Hecho (0018) |
| Score de salud documental (consulta por rol + snapshot diario por el worker) | Hecho (0018) |
| Exportación de legajo (JSON / CSV) con traza | Hecho (0018) |
| Drive de solo lectura: carpeta por tenant, escaneo manual/programado, extracción tipo/sujeto/fecha por confianza en dos niveles (nombre de archivo, y texto embebido de PDF cuando el nombre no alcanza), bandeja de excepciones | Hecho (0018/nivel 2 sin migración; adaptador Google Drive por cuenta de servicio, probado con proveedor simulado) |
| Motor de evaluación puro + 5 casos de oro + orquestación decisión/consulta | Hecho |
| Auth JWT (login/refresh/logout), roles, universo del supervisor, contraseñas por bytes | Hecho |
| Comandos (46) + consultas (32) + storage (3) + salud (2) + público (2) | Hecho |
| Idempotencia por actor con exclusión real; outbox con dedup; revaluación declarativa | Hecho |
| Worker: leases, backoff, dead-letter, purga en dos fases, dos instancias | Hecho |
| Validación técnica de evidencia: formato/tipo de contenido real/PDF no corrupto, malware (`no_configurado` sin scanner real), eje `archivo_validacion` independiente de `estado_confirmacion`, caso A (declarado→`RechazarPropuesta`) / caso B (verificado→notifica + revaluación, nunca toca `estado_confirmacion`), bloquea descarga, fencing por token, recuperación manual (reemplazo o `invalidar_evidencia`) | Hecho (0021) |
| Transporte real a Módulo 2 (hoy `PublicadorEnLog`; el drenaje ya tiene backoff/tope de reintentos/alerta obligatoria — 0020), storage S3, lectura de contenido más allá de tipo/sujeto/fecha (OCR general) | Pendiente / segunda etapa (declarado, no silencioso) |
| Gestión de usuarios por API (alta/cambio/reset de contraseña, reactivación) | Pendiente (CLI `scripts/administracion.py`: tenant, usuarios, desactivación) |
