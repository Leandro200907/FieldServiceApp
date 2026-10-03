"""Evita que pytest use por accidente la base de demo manual (fsm_demo) o una *_demo
en la suite general. Ver README § Tests y .env.test.example."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from _pytest.config import Config

# Bases reservadas a uso humano / demo local; nunca para pytest del agente ni suite general.
_PROHIBIDAS = frozenset({"fsm_demo"})

# Suite general (CI y desarrollo): solo estas bases o sufijo _test explícito.
_PERMITIDAS_SUITE = frozenset({"modulo1_ci", "modulo1_test"})


def _nombre_base(url: str) -> str:
    normalizada = url.replace("postgresql+psycopg://", "postgresql://")
    ruta = urlsplit(normalizada).path.strip("/")
    if not ruta:
        return ""
    return ruta.split("/")[-1].split("?")[0]


def _solo_archivo_sembrar_demo(config: Config) -> bool:
    rutas = [str(a) for a in config.args if str(a) and not str(a).startswith("-")]
    if not rutas:
        return False
    return all("test_sembrar_demo" in r for r in rutas)


def validar_base_para_pytest(config: Config) -> None:
    from app.config import settings

    base = _nombre_base(settings.database_url)
    mig = _nombre_base(os.environ.get("DATABASE_URL_MIGRATIONS", settings.database_url))
    if not base:
        raise SystemExit(
            "pytest abortado: DATABASE_URL sin nombre de base. "
            "Definí ENV_FILE=.env.test (ver backend/.env.test.example)."
        )
    if mig and mig != base:
        raise SystemExit(
            f"pytest abortado: DATABASE_URL ({base}) y DATABASE_URL_MIGRATIONS ({mig}) "
            "deben apuntar a la misma base de tests."
        )

    if base in _PROHIBIDAS:
        raise SystemExit(
            f"pytest abortado: la base '{base}' está reservada a demo manual. "
            "Usá ENV_FILE=.env.test con modulo1_test (suite general) o modulo1_ci_demo "
            "solo para tests/test_sembrar_demo.py."
        )

    if base.endswith("_demo"):
        if not _solo_archivo_sembrar_demo(config):
            raise SystemExit(
                f"pytest abortado: la base '{base}' es de sembrado demo. "
                "La suite general debe usar modulo1_test (ENV_FILE=.env.test). "
                "Para tests de sembrado: pytest tests/test_sembrar_demo.py con modulo1_ci_demo."
            )
        return

    if base in _PERMITIDAS_SUITE or base.endswith("_test"):
        return

    raise SystemExit(
        f"pytest abortado: DATABASE_URL apunta a '{base}', que no es una base de test explícita. "
        f"Permitidas: {', '.join(sorted(_PERMITIDAS_SUITE))} o nombre terminado en _test. "
        "Copiá .env.test.example a .env.test y ejecutá con ENV_FILE=.env.test."
    )
