# FieldServiceApp

SaaS de trazabilidad para empresas de servicios de campo en oil & gas (Vaca Muerta): desde la
orden de compra (OC) de la operadora hasta la certificación y la facturación del servicio.

## Módulos

- **Módulo 1 — Documentación habilitante (en construcción).** Cumplimiento documental de
  personas, equipos, vehículos y empresa frente a lo que exige cada operadora para las OC del
  backlog: legajos, requisitos y matrices por operadora, vencimientos y alertas, radar
  documental, paquete de entrega.
- **Módulo 2 — Ejecución y certificación (en diseño).** Orden de trabajo, parte diario, firma,
  certificación y facturación.

## Mapa del repositorio

| Carpeta | Contenido |
|---|---|
| `backend/` | API FastAPI (Python 3.13), PostgreSQL 16 con RLS por tenant, migraciones Alembic y worker (cola nativa en Postgres). Detalle en [backend/README.md](backend/README.md). |
| `backend/docs/` | Decisiones de dominio, flujos, handoff al frontend y contrato OpenAPI versionado (`openapi.json`). |
| `frontend/` | Cliente React + TypeScript + Vite. Detalle en [frontend/README.md](frontend/README.md). |
| `.github/workflows/` | CI (`ci.yml`): backend (Alembic + pytest + sembrado demo en base de CI) y frontend (`npm run check`). |
| `certificacion-servicios-analisisv3.md` | Análisis de dominio vigente (la v1 está obsoleta). |

## Dónde vive la verdad del dominio

- [backend/docs/DECISIONES_DOMINIO.md](backend/docs/DECISIONES_DOMINIO.md): decisiones cerradas
  de dominio. Si otro documento contradice este, gana este.
- [backend/docs/flujos/](backend/docs/flujos/): flujos detallados (renovación, inducción y
  competencia, etc.).
- [backend/docs/HANDOFF_FRONTEND.md](backend/docs/HANDOFF_FRONTEND.md): contrato funcional para
  el frontend y capacidades todavía no expuestas.
- [backend/docs/openapi.json](backend/docs/openapi.json): contrato HTTP generado desde la app.

## Arranque local en Windows (PowerShell)

Requisitos y bootstrap de la base (roles, base, `.env`, migraciones): ver
[backend/README.md](backend/README.md). Una vez hecho, levantar tres terminales.

**Terminal 1 — API**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:ENV_FILE = ".env"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — worker** (obligatorio: sin él los archivos subidos quedan «en verificación
técnica» y `/v1/salud/listo` informa el worker sin latido)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:ENV_FILE = ".env"
python -m app.worker.main
```

**Terminal 3 — frontend**

```powershell
cd frontend
npm run dev
```

La aplicación abre en http://127.0.0.1:5173 (Vite escucha en `127.0.0.1`; el proxy envía
`/v1` a `http://127.0.0.1:8000`, configurable con `API_PROXY_TARGET` en `.env.local`).

**Salud:** http://127.0.0.1:8000/v1/salud/listo (readiness: base, migración, storage y
worker) y http://127.0.0.1:8000/v1/salud/vivo (liveness).

## Tests y comprobaciones

Backend, siempre contra la base de tests (nunca contra la demo):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:ENV_FILE = ".env.test"
python -m pytest -q --ignore=tests/test_sembrar_demo.py
```

El sembrado demo (`tests/test_sembrar_demo.py`) se prueba solo en CI, contra
`modulo1_ci_demo`.

Frontend (contrato fijado + tipos + tests + build, lo mismo que corre CI):

```powershell
cd frontend
npm run check
```

## Reglas para agentes de IA

Antes de tocar el repo, leer [AGENTS.md](AGENTS.md).
