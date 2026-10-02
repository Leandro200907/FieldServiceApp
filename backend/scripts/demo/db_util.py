"""Conexiones, reset de base _demo y limpieza de storage."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from sqlalchemy import text

RAIZ_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ_BACKEND))

from app.entorno import archivo_de_entorno  # noqa: E402


class ErrorDemo(SystemExit):
    def __init__(self, mensaje: str):
        print(mensaje, file=sys.stderr)
        super().__init__(2)


def leer_env() -> dict[str, str]:
    ruta = Path(archivo_de_entorno())
    valores: dict[str, str] = {}
    if ruta.is_file():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip()
    for k in ("DATABASE_URL", "DATABASE_URL_MIGRATIONS"):
        if os.environ.get(k):
            valores[k] = os.environ[k]
    return valores


def _normalizar_dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def nombre_base_desde_url(url: str) -> str:
    parsed = urlparse(_normalizar_dsn(url))
    if not parsed.path or parsed.path == "/":
        raise ErrorDemo(f"URL sin nombre de base: {url}")
    return parsed.path.lstrip("/").split("?")[0]


def exigir_base_demo() -> tuple[str, str, str]:
    """Devuelve (dsn_app, dsn_owner, nombre_base). Aborta si no termina en _demo o difieren."""
    env = leer_env()
    app = env.get("DATABASE_URL")
    owner = env.get("DATABASE_URL_MIGRATIONS")
    if not app or not owner:
        raise ErrorDemo("Faltan DATABASE_URL y DATABASE_URL_MIGRATIONS")
    app_n = nombre_base_desde_url(app)
    own_n = nombre_base_desde_url(owner)
    if not app_n.endswith("_demo") or not own_n.endswith("_demo"):
        raise ErrorDemo(f"Aborto: el nombre de la base debe terminar en _demo (app={app_n}, migrations={own_n})")
    if app_n != own_n:
        raise ErrorDemo(f"Aborto: DATABASE_URL ({app_n}) y DATABASE_URL_MIGRATIONS ({own_n}) deben apuntar a la misma base")
    return _normalizar_dsn(app), _normalizar_dsn(owner), app_n


def _dsn_admin_para_reset(dsn_owner: str) -> str:
    """Superusuario o rol con CREATEDB para DROP/CREATE (p. ej. postgres en CI)."""
    url = os.environ.get("DATABASE_URL_ADMIN")
    if url:
        return _normalizar_dsn(url)
    return re.sub(r"/[^/]+$", "/postgres", dsn_owner)


def reset_base(dsn_owner: str, nombre_base: str) -> None:
    """DROP/CREATE DATABASE y alembic upgrade head."""
    admin = _dsn_admin_para_reset(dsn_owner)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (nombre_base,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{nombre_base}"')
        conn.execute(f'CREATE DATABASE "{nombre_base}" OWNER modulo1_owner')
    env = os.environ.copy()
    env_file = archivo_de_entorno()
    if env_file:
        env["ENV_FILE"] = env_file
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=RAIZ_BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise ErrorDemo(f"alembic upgrade head falló:\n{r.stderr or r.stdout}")


def tenant_ids_por_slugs(dsn_owner: str, slugs: list[str]) -> dict[str, str]:
    """Consulta cross-tenant previa al reset; usa rol owner (RLS no aplica)."""
    if not slugs:
        return {}
    with psycopg.connect(dsn_owner) as conn:
        filas = conn.execute(
            "SELECT slug, tenant_id::text FROM modulo1.tenant WHERE slug = ANY(%s)",
            (slugs,),
        ).fetchall()
    return {s: t for s, t in filas}


def borrar_storage_tenants(tenant_ids: list[str]) -> int:
    from app.config import settings
    from app.storage.local import StorageLocal

    if not tenant_ids:
        return 0
    base = Path(settings.storage_local_dir).resolve()
    if not base.is_dir():
        return 0
    storage = StorageLocal()
    borrados = 0
    for tid in tenant_ids:
        prefijo = f"{tid}/"
        for path in base.rglob("*"):
            if path.is_file():
                rel = path.relative_to(base).as_posix()
                if rel.startswith(prefijo):
                    if storage.borrar(rel):
                        borrados += 1
    return borrados


def precargar_plantillas_json(ruta: Path) -> None:
    import importlib.util

    _, dsn_owner, _ = exigir_base_demo()
    mod_path = RAIZ_BACKEND / "scripts" / "precargar_plantillas.py"
    spec = importlib.util.spec_from_file_location("precargar_plantillas", mod_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    datos = __import__("json").loads(ruta.read_text(encoding="utf-8"))
    with psycopg.connect(dsn_owner) as conn:
        mod.precargar(conn, datos)
        conn.commit()
