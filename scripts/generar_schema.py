"""Genera `docs_schema_actual.sql`: esquema (sin datos, sin propietarios, sin privilegios)
de una base creada DESDE CERO y migrada hasta el head.

    ENV_FILE=.env.boot .venv/Scripts/python scripts/generar_schema.py

Usa `DATABASE_URL_MIGRATIONS` del ENV_FILE (rol owner, sólo lectura acá) y `pg_dump`
(`PG_DUMP` para indicar el binario). Exige que la base esté exactamente en
`app.version.MIGRACION_HEAD`; si no, aborta: el dump documenta el head, no "lo que haya".
Se eliminan las líneas volátiles de pg_dump (`\\restrict`, versiones, `SET`, comentarios
vacíos) para que el archivo sea estable y comparable en git. Nunca contiene contraseñas:
las credenciales viajan sólo en la variable de entorno del proceso hijo.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.entorno import archivo_de_entorno  # noqa: E402
from app.version import MIGRACION_HEAD  # noqa: E402

DESTINO = RAIZ / "docs_schema_actual.sql"
_VOLATILES = re.compile(r"^(\\restrict|\\unrestrict|SET |SELECT pg_catalog\.set_config|-- Dumped|--$|\s*$)")


def _dsn_migraciones() -> str:
    ruta = Path(archivo_de_entorno())
    valores: dict[str, str] = {}
    if ruta.is_file():  # misma precedencia que app.config: proceso > ENV_FILE > .env
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip()
    dsn = os.environ.get("DATABASE_URL_MIGRATIONS") or valores.get("DATABASE_URL_MIGRATIONS")
    if not dsn:
        raise SystemExit("Falta DATABASE_URL_MIGRATIONS (en el entorno o en el ENV_FILE)")
    return dsn.replace("postgresql+psycopg://", "postgresql://")


def _head_aplicado(dsn: str) -> str | None:
    import psycopg

    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def generar(dsn: str) -> str:
    aplicado = _head_aplicado(dsn)
    if aplicado != MIGRACION_HEAD:
        raise SystemExit(f"La base está en {aplicado!r}, el código espera {MIGRACION_HEAD!r}: migrá antes de generar el dump")
    partes = urlsplit(dsn)
    entorno = {**os.environ, "PGPASSWORD": partes.password or ""}
    url_sin_password = partes._replace(netloc=f"{partes.username}@{partes.hostname}:{partes.port or 5432}").geturl()
    salida = subprocess.run(
        [os.environ.get("PG_DUMP", "pg_dump"), "--schema-only", "--no-owner", "--no-privileges", "--no-comments",
         "--schema=modulo1", "--schema=plataforma", url_sin_password],
        env=entorno, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    lineas = [ln.rstrip() for ln in salida.splitlines() if not _VOLATILES.match(ln)]
    cabecera = [
        "-- docs_schema_actual.sql — esquema de Módulo 1 generado por scripts/generar_schema.py",
        f"-- head: {MIGRACION_HEAD}",
        "-- Base creada desde cero (scripts/crear_roles.sql → scripts/crear_base.sql → alembic upgrade head),",
        "-- pg_dump --schema-only --no-owner --no-privileges. Sin datos ni credenciales. No editar a mano.",
        "",
    ]
    return "\n".join(cabecera + lineas) + "\n"


def main() -> int:
    contenido = generar(_dsn_migraciones())
    DESTINO.write_text(contenido, encoding="utf-8")
    print(f"{DESTINO.name}: {contenido.count(chr(10))} líneas, head {MIGRACION_HEAD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
