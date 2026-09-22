"""ENV_FILE: API, worker, Alembic y scripts resuelven el mismo archivo de entorno con la
misma precedencia (proceso > ENV_FILE > `.env` sólo si ENV_FILE no está). Se arrancan la
API y el worker en procesos separados con dos archivos distintos y se comprueba, por su
log de arranque, cuál usaron. Ese log nunca lleva secretos ni el DSN completo."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.config import settings
from app.entorno import archivo_de_entorno

RAIZ = Path(__file__).resolve().parents[1]
PASSWORD_DSN = urlsplit(settings.database_url).password or ""

ARRANQUE_API = (
    "import logging; logging.basicConfig(level='INFO', format='%(name)s %(message)s')\n"
    "from fastapi.testclient import TestClient\n"
    "from app.main import app\n"
    "with TestClient(app) as c:\n"
    "    print('vivo', c.get('/v1/salud/vivo').status_code)\n"
)


def _env_file(ruta: Path, zona: str) -> Path:
    ruta.write_text(
        f"DATABASE_URL={settings.database_url}\nJWT_SECRET={settings.jwt_secret}\nSTORAGE_SECRET={settings.storage_secret}\n"
        f"STORAGE_LOCAL_DIR={ruta.parent / 'storage'}\nTENANT_DEFAULT_TIMEZONE={zona}\nWORKER_POLL_SEG=9\n",
        encoding="utf-8",
    )
    return ruta


def _correr(args: list[str], env_file: str | None, cwd: Path, extra_env: dict[str, str] | None = None) -> str:
    # Entorno mínimo: sin las variables del proceso de pytest que podrían pisar el archivo.
    entorno = {k: v for k, v in os.environ.items() if k not in ("ENV_FILE", "TENANT_DEFAULT_TIMEZONE", "DATABASE_URL")}
    entorno["PYTHONPATH"] = str(RAIZ)
    entorno["PYTHONIOENCODING"] = "utf-8"
    if env_file is not None:
        entorno["ENV_FILE"] = env_file
    entorno.update(extra_env or {})
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True, encoding="utf-8", cwd=cwd, env=entorno, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout + r.stderr


@pytest.fixture
def dos_archivos(tmp_path):
    a = _env_file(tmp_path / "a.env", "America/Argentina/Buenos_Aires")
    b = _env_file(tmp_path / "b.env", "UTC")
    return a, b


def _sin_secretos(salida: str) -> None:
    assert PASSWORD_DSN and PASSWORD_DSN not in salida
    assert settings.jwt_secret not in salida and settings.storage_secret not in salida
    assert "postgresql" not in salida


def test_api_arranca_con_el_archivo_indicado(dos_archivos, tmp_path):
    a, b = dos_archivos
    sa = _correr(["-c", ARRANQUE_API], str(a), tmp_path)
    sb = _correr(["-c", ARRANQUE_API], str(b), tmp_path)
    assert "vivo 200" in sa and "vivo 200" in sb
    assert f"'env_file': '{a}'" in sa.replace("\\\\", "\\") and "'zona_horaria': 'America/Argentina/Buenos_Aires'" in sa
    assert f"'env_file': '{b}'" in sb.replace("\\\\", "\\") and "'zona_horaria': 'UTC'" in sb
    _sin_secretos(sa)
    _sin_secretos(sb)


def test_worker_arranca_con_el_archivo_indicado(dos_archivos, tmp_path):
    a, b = dos_archivos
    sa = _correr(["-m", "app.worker.main", "--una-vuelta"], str(a), tmp_path)
    sb = _correr(["-m", "app.worker.main", "--una-vuelta"], str(b), tmp_path)
    assert "worker arranca" in sa and "vuelta:" in sa
    assert f"'env_file': '{a}'" in sa.replace("\\\\", "\\") and "'zona_horaria': 'America/Argentina/Buenos_Aires'" in sa
    assert f"'env_file': '{b}'" in sb.replace("\\\\", "\\") and "'zona_horaria': 'UTC'" in sb
    _sin_secretos(sa)
    _sin_secretos(sb)


def test_api_y_worker_usan_el_mismo_archivo(dos_archivos, tmp_path):
    _, b = dos_archivos
    api = _correr(["-c", ARRANQUE_API], str(b), tmp_path)
    worker = _correr(["-m", "app.worker.main", "--una-vuelta"], str(b), tmp_path)
    for salida in (api, worker):
        assert f"'env_file': '{b}'" in salida.replace("\\\\", "\\") and "'zona_horaria': 'UTC'" in salida
        assert f"'base': '{urlsplit(settings.database_url).path.lstrip('/')}'" in salida


def test_precedencia_proceso_sobre_archivo(dos_archivos, tmp_path):
    _, b = dos_archivos
    salida = _correr(["-c", ARRANQUE_API], str(b), tmp_path, {"TENANT_DEFAULT_TIMEZONE": "Europe/Madrid"})
    assert "'zona_horaria': 'Europe/Madrid'" in salida and "'zona_horaria': 'UTC'" not in salida


def test_punto_env_solo_si_env_file_no_esta(dos_archivos, tmp_path):
    a, _ = dos_archivos
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _env_file(cwd / ".env", "Asia/Tokyo")
    sin = _correr(["-c", ARRANQUE_API], None, cwd)                 # sin ENV_FILE → .env del cwd
    assert "'env_file': '.env'" in sin and "'zona_horaria': 'Asia/Tokyo'" in sin
    con = _correr(["-c", ARRANQUE_API], str(a), cwd)               # con ENV_FILE → NO se lee .env
    assert "'zona_horaria': 'America/Argentina/Buenos_Aires'" in con and "Tokyo" not in con


def test_alembic_y_generar_schema_resuelven_igual(tmp_path, monkeypatch):
    monkeypatch.delenv("ENV_FILE", raising=False)
    assert archivo_de_entorno() == ".env"
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "x.env"))
    assert archivo_de_entorno() == str(tmp_path / "x.env")
    # migrations/env.py y scripts/generar_schema.py importan esta misma función
    assert "from app.entorno import archivo_de_entorno" in (RAIZ / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "from app.entorno import archivo_de_entorno" in (RAIZ / "scripts" / "generar_schema.py").read_text(encoding="utf-8")
    assert "from app.entorno import archivo_de_entorno" in (RAIZ / "app" / "config.py").read_text(encoding="utf-8")
