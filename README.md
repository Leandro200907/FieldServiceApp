# Módulo 1 — Documentación habilitante (implementación)

Arranque de código, siguiendo al pie lo cerrado en los documentos de diseño del Project
("Field Service Management"): `modulo1-documentacion-habilitante.md`, `modulo1-modelo-dominio.md`,
`modulo1-especificacion.md`, `modulo1-no-funcionales.md`, `modulo1-arquitectura-tecnica.md`,
`modulo1-wireframes-api.md`.

Este README se actualiza a medida que se agregan piezas. No es documentación de diseño —
esa vive en el Project. Esto es la bitácora de qué existe en el código y cómo correrlo.

## Stack

- Python 3.11+, FastAPI (API), SQLAlchemy 2.0 (ORM), Alembic (migraciones), PostgreSQL.
- pytest para tests, incluida la suite de casos de oro del motor de evaluación (obligatoria
  en cada cambio, per 8.6 de arquitectura-tecnica.md).
- Sin librería de cola de terceros todavía: 8.4 dejó la elección de librería como detalle de
  implementación — se define cuando el volumen real lo pida; mientras tanto, patrón a mano
  sobre Postgres (`SELECT ... FOR UPDATE SKIP LOCKED`) con lease/expiración explícita.

## Estructura

```
app/
  config.py          # settings (env vars), sin secretos hardcodeados
  db.py               # engine, session factory, contexto de tenant (SET LOCAL, 8.1)
  main.py             # FastAPI app, monta los routers de cada módulo
  core/
    tipos.py          # value objects puros del motor (sin ORM, sin I/O)
    evaluacion.py      # motor de evaluación de habilitación — función pura (1.9, 4.1 de especificacion.md)
  auth/
    jwt.py             # emisión/validación de JWT (9.2)
    dependencies.py     # dependency de FastAPI que resuelve tenant_id + usuario desde el token
  modules/
    legajos/           # Legajo, Documento, Acreditación, Inducción, Asignación de supervisor,
                        # Lote de importación, CustodiaDelRecurso (dominio "Evidencia" + "Operación" parcial)
    requisitos/         # Definición de requisito, Matriz de requisitos, Línea de requisito,
                        # Requisito particular
    operacion/          # Evaluación de habilitación (persistida), Excepción, Constancia del cliente,
                        # Alerta de vencimiento, Aviso de revaluación, Aviso de incumplimiento
    oc/                 # Vista de compromiso (proyección) + backlog de OC standalone (1.12)
migrations/            # Alembic
tests/
  test_casos_de_oro.py # Los 5 casos de oro de especificacion.md, sección 6 — el motor no se
                        # considera correcto si no los pasa todos.
```

## Cómo correr (local, con Postgres ya levantado)

```bash
cp .env.example .env   # completar DATABASE_URL, JWT_SECRET
pip install -r requirements.txt
alembic upgrade head
pytest
uvicorn app.main:app --reload
```

## Estado de avance

| Pieza | Estado |
|---|---|
| Bootstrap del proyecto (estructura, config, conexión con tenant) | Hecho |
| Migración inicial (schema `modulo1`, RLS, tablas base) | Hecho |
| Motor de evaluación puro + casos de oro | Hecho |
| Endpoints de comandos (9.3) | Pendiente — candidato a subagente en paralelo |
| Endpoints de consultas (9.4) | Pendiente — candidato a subagente en paralelo |
| Worker (outbox, notificaciones, storage) | Pendiente — candidato a subagente en paralelo |
| Auth (JWT, dependency de tenant) | Pendiente |
