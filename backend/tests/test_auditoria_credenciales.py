"""A-01 / M-07 de la auditoría: la API y el worker no deben conocer ni cargar la credencial
del owner; los roles no se crean desde Alembic con contraseña por defecto."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _python_sin_variable(codigo: str, *quitar: str) -> subprocess.CompletedProcess:
    # ENV_FILE apunta a un archivo inexistente en los códigos de abajo, así que la app sólo
    # ve variables del proceso: se le dan las mínimas (nunca DATABASE_URL_MIGRATIONS).
    from app.config import settings
    env = {k: v for k, v in os.environ.items() if k not in quitar}
    env.update({"DATABASE_URL": settings.database_url, "JWT_SECRET": settings.jwt_secret, "STORAGE_SECRET": settings.storage_secret})
    env["PYTHONPATH"] = str(RAIZ)
    return subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True, cwd=RAIZ,
                          stdin=subprocess.DEVNULL, timeout=60)


def test_a01_la_app_arranca_sin_credencial_de_migraciones(monkeypatch):
    """Sin DATABASE_URL_MIGRATIONS en el entorno (ni en .env), `app.main` importa igual y
    `app.db` no expone ningún engine con la credencial del owner."""
    # .env local puede tener la variable: se neutraliza apuntando a un .env vacío.
    codigo = (
        "import os; os.environ['ENV_FILE']='no-existe.env';"
        "import app.db, app.main;"
        "assert not hasattr(app.db, 'migrations_engine');"
        "from app.config import settings;"
        "assert not hasattr(settings, 'database_url_migrations');"
        "print('ok')"
    )
    r = _python_sin_variable(codigo, "DATABASE_URL_MIGRATIONS")
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


def test_a01_alembic_exige_la_variable_y_no_la_toma_de_settings():
    """migrations/env.py lee DATABASE_URL_MIGRATIONS del entorno, nunca de app.config, y
    falla con un mensaje claro si falta."""
    codigo = (
        "import os; os.environ['ENV_FILE']='no-existe.env';"
        "from alembic.config import Config; from alembic import command;"
        "cfg = Config('alembic.ini');"
        "command.current(cfg)"
    )
    r = _python_sin_variable(codigo, "DATABASE_URL_MIGRATIONS")
    assert r.returncode != 0 and "DATABASE_URL_MIGRATIONS" in (r.stderr + r.stdout)


def test_m07_ninguna_migracion_crea_roles_con_password():
    for archivo in (RAIZ / "migrations" / "versions").glob("*.py"):
        contenido = archivo.read_text(encoding="utf-8")
        assert "CREATE ROLE" not in contenido.upper(), archivo.name
        assert not re.search(r"PASSWORD\s+'", contenido, re.IGNORECASE), archivo.name


def test_m07_script_de_roles_no_tiene_password_por_defecto():
    script = (RAIZ / "scripts" / "crear_roles.sql").read_text(encoding="utf-8")
    assert "changeme" not in script.lower()
    # las contraseñas entran como variables de psql, obligatorias
    assert ":'owner_password'" in script and ":'app_password'" in script
