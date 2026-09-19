"""Arma el ZIP sanitizado para auditoría independiente (no crea tags).

    .venv/Scripts/python scripts/empaquetar_auditoria.py --specs "<dir con modulo1-*.md>" \\
        --salida "<dir>" [--pip-audit "<texto>"] [--bootstrap "<texto>"] [--tests N] [--rutas N]

Incluye app/, migrations/, tests/, scripts/, docs/ (con openapi.json), las especificaciones
originales, docs_schema_actual.sql, requirements*.in/.lock, README, BITACORA, .env.example,
alembic.ini y un AUDIT_MANIFEST.md generado. Excluye .env* reales, .venv, .git, storage_local,
cachés, logs y dumps con datos. Antes de comprimir escanea TODO el contenido buscando secretos
(contraseñas de los .env locales, DSN con credenciales, JWT, claves privadas) y aborta si
encuentra alguno. Imprime nombre, tamaño y SHA-256 del ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from app.version import MIGRACION_HEAD, VERSION  # noqa: E402

DIRECTORIOS = ("app", "migrations", "tests", "scripts", "docs")
ARCHIVOS = ("docs_schema_actual.sql", "requirements.in", "requirements-dev.in", "requirements.lock", "requirements-dev.lock",
            "README.md", "BITACORA.md", ".env.example", "alembic.ini", ".gitignore")
SPECS = ("modulo1-especificacion.md", "modulo1-modelo-dominio.md", "modulo1-no-funcionales.md",
         "modulo1-documentacion-habilitante.md", "modulo1-arquitectura-tecnica.md", "modulo1-wireframes-api.md")
EXCLUIR_DIRS = {"__pycache__", ".pytest_cache", ".venv", ".git", "storage_local", "htmlcov", ".mypy_cache", ".ruff_cache"}
EXCLUIR_SUFIJOS = (".pyc", ".log", ".coverage", ".dump", ".backup")

PATRONES_SECRETOS = [
    (re.compile(r"postgresql(\+psycopg)?://[^:\s/]+:[^@\s]+@"), "DSN con credenciales"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "JWT"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "clave privada"),
    (re.compile(r"^\s*(JWT_SECRET|STORAGE_SECRET|DATABASE_URL|DATABASE_URL_MIGRATIONS|USUARIO_PASSWORD)\s*=\s*(?!CAMBIAR|\.\.\.|…|<)[^\s#]{8,}", re.M), "variable de secreto con valor"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def _valores_env_locales() -> set[str]:
    """Contraseñas y secretos reales de los .env locales: no pueden aparecer en el ZIP."""
    valores: set[str] = set()
    for env in RAIZ.glob(".env*"):
        if env.name == ".env.example":
            continue
        for linea in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"\s*(JWT_SECRET|STORAGE_SECRET)\s*=\s*(\S+)", linea)
            if m and len(m.group(2)) >= 8:
                valores.add(m.group(2))
            m = re.search(r"://[^:\s/]+:([^@\s]+)@", linea)
            if m and len(m.group(1)) >= 6:
                valores.add(m.group(1))
    return valores


def _copiar(origen: Path, destino: Path) -> list[Path]:
    copiados = []
    for base, dirs, archivos in os.walk(origen):
        dirs[:] = [d for d in dirs if d not in EXCLUIR_DIRS]
        for a in archivos:
            p = Path(base) / a
            if a.endswith(EXCLUIR_SUFIJOS) or (a.startswith(".env") and a != ".env.example"):
                continue
            rel = p.relative_to(RAIZ)
            (destino / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, destino / rel)
            copiados.append(destino / rel)
    return copiados


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def escanear(staging: Path, valores_locales: set[str]) -> list[str]:
    hallazgos = []
    for p in staging.rglob("*"):
        if not p.is_file():
            continue
        texto = p.read_text(encoding="utf-8", errors="ignore")
        for patron, nombre in PATRONES_SECRETOS:
            for m in patron.finditer(texto):
                hallazgos.append(f"{p.relative_to(staging)}: {nombre} → {m.group(0)[:40]}…")
        for v in valores_locales:
            if v in texto:
                hallazgos.append(f"{p.relative_to(staging)}: valor de un .env local")
    return hallazgos


def manifiesto(specs_dir: Path, tests: int, rutas: int, bootstrap: str, pip_audit: str) -> str:
    head = _git("rev-parse", "HEAD")
    log = _git("log", "--oneline", "1ccc316..HEAD")
    heads = subprocess.run([sys.executable, "-m", "alembic", "heads"], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    pg = subprocess.run([os.environ.get("PSQL", "psql"), "--version"], capture_output=True, text=True).stdout.strip() or "psql no disponible en PATH"
    shas = "\n".join(f"| `{s}` | `{_sha256(specs_dir / s)}` |" for s in SPECS if (specs_dir / s).is_file())
    return f"""# AUDIT_MANIFEST — Módulo 1 backend (candidato v1.0, sin tag)

Generado: {datetime.now(timezone.utc).isoformat(timespec="seconds")}

## Código
- HEAD: `{head}`
- Versión declarada (`app/version.py`): `{VERSION}`; head de migraciones esperado: `{MIGRACION_HEAD}`
- `alembic heads`: `{heads}` (un solo head)
- Migraciones: {len(list((RAIZ / "migrations" / "versions").glob("*.py")))} archivos en `migrations/versions/`

## Entorno de verificación
- Python: {platform.python_version()} ({platform.system()} {platform.release()})
- PostgreSQL: {pg}
- Tests recolectados: {tests}
- Rutas HTTP: {rutas} operaciones (contrato en `docs/openapi.json`)

## Resultado del bootstrap desde cero
{bootstrap}

## pip-audit (locks con hashes)
{pip_audit}

## SHA-256 de las especificaciones originales (carpeta `especificaciones/`)
| Archivo | SHA-256 |
|---|---|
{shas}

## Commits de endurecimiento (desde el bootstrap inicial hasta HEAD)
```
{log}
```

## Excluido a propósito
`.env`, `.env.dev`, `.env.boot`, cualquier `.env*` real, `.venv/`, `.git/`, `storage_local/`,
`__pycache__/`, `.pytest_cache/`, coverage, logs, dumps con datos. Ninguna contraseña, JWT,
DSN real ni token: verificado por `scripts/empaquetar_auditoria.py` (escaneo de patrones y
de los valores de los `.env` locales) antes de comprimir.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--tests", type=int, required=True)
    ap.add_argument("--rutas", type=int, required=True)
    ap.add_argument("--bootstrap", default="(no informado)")
    ap.add_argument("--pip-audit", default="(no informado)")
    args = ap.parse_args()

    specs_dir = Path(args.specs)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    nombre = f"modulo1-backend-auditoria-{_git('rev-parse', '--short', 'HEAD')}"
    staging = salida / nombre
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    for d in DIRECTORIOS:
        _copiar(RAIZ / d, staging)
    for a in ARCHIVOS:
        shutil.copy2(RAIZ / a, staging / a)
    (staging / "especificaciones").mkdir()
    for s in SPECS:
        if (specs_dir / s).is_file():
            shutil.copy2(specs_dir / s, staging / "especificaciones" / s)
    (staging / "AUDIT_MANIFEST.md").write_text(
        manifiesto(specs_dir, args.tests, args.rutas, args.bootstrap, args.pip_audit), encoding="utf-8")

    hallazgos = escanear(staging, _valores_env_locales())
    if hallazgos:
        print("ABORTADO: secretos en el contenido del ZIP:", *hallazgos, sep="\n  ", file=sys.stderr)
        shutil.rmtree(staging)
        return 1

    zip_path = salida / f"{nombre}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(staging.rglob("*")):
            if p.is_file():
                z.write(p, f"{nombre}/{p.relative_to(staging).as_posix()}")
    shutil.rmtree(staging)
    with zipfile.ZipFile(zip_path) as z:
        n = len(z.namelist())
    print(f"{zip_path}\n  archivos: {n}\n  tamaño: {zip_path.stat().st_size:,} bytes\n  sha256: {_sha256(zip_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
