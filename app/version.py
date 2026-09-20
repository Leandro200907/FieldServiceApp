"""Versión del backend y head de migraciones que este código espera.

`MIGRACION_HEAD` se compara en readiness (`/v1/salud/listo`) con `alembic_version` de la
base: si difieren, la instancia no está lista (migración atrasada o código viejo). El test
`tests/test_docs_actualizados.py` verifica que coincida con el head real de `migrations/`
y con lo documentado (README, docs_schema_actual.sql).
"""
VERSION = "1.0.0-rc1"
MIGRACION_HEAD = "0017_alertas_vencimiento"
