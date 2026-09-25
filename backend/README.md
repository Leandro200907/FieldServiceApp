Warning: truncated output (original token count: 3609)
Total output lines: 242

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

- **Rutas HTTP:** 92 operaciones sobre 91 paths bajo `/v1` (OpenAPI en `/docs`).
- **Migraciones:** 24 archivos en `migrations/versions/`, un solo head: `0021_validacion_evidencia`.
- **Tests:** 626 (pytest, contra PostgreSQL real; incluyen los 5 casos de oro, E2E HTTP,
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
  config.py / entorno.py # settings desde entorno (precedencia proceso > ENV_FILE > .env); n…2609 tokens truncated…señado, no activo |
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

