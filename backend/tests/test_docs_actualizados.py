"""M-09: la documentación no puede quedar desactualizada en silencio.

- `app.version.MIGRACION_HEAD` == head real de `migrations/`;
- `docs_schema_actual.sql` declara ese head y contiene TODOS los objetos (tablas, índices,
  constraints, funciones) del esquema vivo — si una migración agrega algo y nadie regenera
  el dump, este test falla;
- README declara el head y cifras reales (rutas, migraciones, tests);
- `docs/HANDOFF_FRONTEND.md` lista cada ruta HTTP expuesta."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.db import tenant_session
from app.version import MIGRACION_HEAD

RAIZ = Path(__file__).resolve().parents[1]
DUMP = (RAIZ / "docs_schema_actual.sql").read_text(encoding="utf-8")
README = (RAIZ / "README.md").read_text(encoding="utf-8")
HANDOFF = (RAIZ / "docs" / "HANDOFF_FRONTEND.md").read_text(encoding="utf-8")


def _head_real() -> str:
    heads = ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_heads()
    assert len(heads) == 1, heads
    return heads[0]


def test_version_declara_el_head_real():
    assert MIGRACION_HEAD == _head_real()


def test_dump_declara_el_head_y_no_lleva_credenciales_ni_propietarios():
    assert f"-- head: {MIGRACION_HEAD}\n" in DUMP
    assert "OWNER TO" not in DUMP and "GRANT " not in DUMP and "REVOKE " not in DUMP
    assert not re.search(r"PASSWORD\s+'", DUMP, re.I) and "://" not in DUMP     # ni contraseñas de roles ni DSN
    assert "\restrict" not in DUMP and "COPY " not in DUMP and not re.search(r"^INSERT INTO", DUMP, re.M)


def test_dump_contiene_todos_los_objetos_del_esquema_vivo():
    with tenant_session("00000000-0000-0000-0000-000000000000") as s:
        tablas = [r[0] for r in s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname IN ('modulo1','plataforma')"))]
        indices = [r[0] for r in s.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname IN ('modulo1','plataforma')"))]
        constraints = [r[0] for r in s.execute(text(
            "SELECT conname FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname IN ('modulo1','plataforma') AND conname NOT LIKE '%_not_null'"))]
        funciones = [r[0] for r in s.execute(text(
            "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname IN ('modulo1','plataforma')"))]
        columnas = [f"{r[0]}.{r[1]}" for r in s.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema IN ('modulo1','plataforma')"))]
    faltan = [n for n in tablas + indices + constraints + funciones if n not in DUMP]
    assert not faltan, f"objetos del esquema vivo ausentes en docs_schema_actual.sql (regenerar con scripts/generar_schema.py): {faltan}"
    # columnas: cada (tabla, columna) aparece dentro del CREATE TABLE correspondiente
    for tabla_col in columnas:
        tabla, col = tabla_col.split(".", 1)
        bloque = re.search(rf"CREATE TABLE \w+\.{tabla} \((.*?)\n\);", DUMP, re.S)
        assert bloque and re.search(rf"^\s+{re.escape(col)} ", bloque.group(1), re.M), f"columna {tabla_col} ausente en el dump"


def _cifra(patron: str, texto: str) -> int:
    m = re.search(patron, texto)
    assert m, patron
    return int(m.group(1))


def test_readme_declara_head_y_cifras_reales(cliente_api):
    assert f"`{MIGRACION_HEAD}`" in README
    paths = cliente_api.get("/openapi.json").json()["paths"]
    operaciones = sum(len(ops) for ops in paths.values())
    migraciones = len([p for p in (RAIZ / "migrations" / "versions").glob("*.py")])
    assert _cifra(r"\*\*Rutas HTTP:\*\* (\d+)", README) == operaciones
    assert _cifra(r"\*\*Migraciones:\*\* (\d+)", README) == migraciones
    salida = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:warnings", str(RAIZ / "tests")],
                            capture_output=True, text=True, cwd=RAIZ).stdout
    recolectados = int(re.search(r"(\d+) tests? collected", salida).group(1))
    assert _cifra(r"\*\*Tests:\*\* (\d+)", README) == recolectados


def test_handoff_frontend_lista_todas_las_rutas(cliente_api):
    paths = cliente_api.get("/openapi.json").json()["paths"]
    faltan = [f"{m.upper()} {p}" for p, ops in paths.items() for m in ops if f"`{m.upper()} {p}`" not in HANDOFF]
    assert not faltan, f"rutas sin documentar en docs/HANDOFF_FRONTEND.md: {faltan}"
    assert f"`{MIGRACION_HEAD}`" in HANDOFF
