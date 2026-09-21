"""Resolución del archivo de entorno — sin efectos secundarios, importable desde Alembic y
scripts que no pueden cargar `app.config` (no tienen DATABASE_URL).

Precedencia (única para API, worker, Alembic y scripts):
  1. variables reales del proceso;
  2. el archivo indicado por ENV_FILE, si la variable está definida;
  3. `.env` del directorio de trabajo, sólo si ENV_FILE no fue indicado.
"""
from __future__ import annotations

import os


def archivo_de_entorno() -> str:
    return os.environ.get("ENV_FILE") or ".env"
