"""Tests del sembrado demo (requieren Postgres con base *_demo en DATABASE_URL)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import tenant_session

RAIZ = Path(__file__).resolve().parents[1]


def _nombre_base() -> str | None:
    url = os.environ.get("DATABASE_URL", "")
    if not url or "/" not in url:
        return None
    return url.rsplit("/", 1)[-1].split("?")[0]


def _exigir_base_demo_tests():
    nb = _nombre_base()
    if not nb or not nb.endswith("_demo"):
        pytest.fail("DATABASE_URL debe apuntar a una base que termine en _demo (job Pytest sembrado demo en CI)")


@pytest.fixture(scope="module")
def demo_sembrado():
    _exigir_base_demo_tests()
    env = os.environ.copy()
    env.setdefault("DEMO_PASSWORD", "demo-secreto-12")
    r = subprocess.run(
        [sys.executable, "scripts/sembrar_demo.py", "--reset"],
        cwd=RAIZ,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr or r.stdout
    return r.stdout


def test_aborta_si_base_no_es_demo(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost/modulo1")
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql+psycopg://owner:own@localhost/modulo1")
    from scripts.demo.db_util import ErrorDemo, exigir_base_demo

    with pytest.raises(ErrorDemo):
        exigir_base_demo()


def test_aborta_si_urls_distintas(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost/fsm_demo")
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", "postgresql+psycopg://owner:own@localhost/otra_demo")
    from scripts.demo.db_util import ErrorDemo, exigir_base_demo

    with pytest.raises(ErrorDemo):
        exigir_base_demo()


def test_cantidades_demo(demo_sembrado):
    _exigir_base_demo_tests()
    from app.db import platform_session

    slugs = ("patagonia-demo", "anelo-demo", "neuquen-demo")
    ids = {}
    with platform_session() as ps:
        for slug in slugs:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            if tid:
                ids[slug] = str(tid)
    assert len(ids) == 3
    for slug in slugs:
        tid = ids[slug]
        with tenant_session(tid) as s:
            n_users = s.execute(text("SELECT count(*) FROM modulo1.usuario WHERE tenant_id = :t"), {"t": tid}).scalar()
            n_active = s.execute(
                text("SELECT count(*) FROM modulo1.usuario WHERE tenant_id = :t AND activo"), {"t": tid}
            ).scalar()
            n_oc = s.execute(text("SELECT count(*) FROM modulo1.oc WHERE tenant_id = :t"), {"t": tid}).scalar()
            assert n_users == 13 and n_active == 12
            assert n_oc >= 6
            tecnicos = s.execute(
                text("SELECT count(DISTINCT sujeto_id) FROM modulo1.usuario WHERE tenant_id = :t AND activo AND 'tecnico' = ANY(roles)"),
                {"t": tid},
            ).scalar()
            docs_tec = s.execute(
                text(
                    "SELECT count(*) FROM modulo1.documento d "
                    "JOIN modulo1.usuario u ON u.sujeto_id = d.sujeto_id AND u.tenant_id = d.tenant_id "
                    "WHERE d.tenant_id = :t AND u.activo AND 'tecnico' = ANY(u.roles)"
                ),
                {"t": tid},
            ).scalar()
            assert tecnicos == 3
            assert docs_tec >= 15


def test_aislamiento_entre_tenants(demo_sembrado):
    _exigir_base_demo_tests()
    from app.db import platform_session

    slugs = ("patagonia-demo", "anelo-demo")
    ids: list[tuple[str, str]] = []
    with platform_session() as ps:
        for slug in slugs:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            assert tid is not None
            ids.append((slug, str(tid)))
    tid_a = ids[0][1]
    slug_b = ids[1][0]
    with tenant_session(tid_a) as s:
        n_b = s.execute(
            text("SELECT count(*) FROM modulo1.usuario WHERE tenant_id = :t AND email LIKE :p"),
            {"t": tid_a, "p": f"%@{slug_b}.demo.test"},
        ).scalar()
        assert n_b == 0


def test_reset_idempotente_en_cantidades(demo_sembrado):
    _exigir_base_demo_tests()
    env = os.environ.copy()
    env.setdefault("DEMO_PASSWORD", "demo-secreto-12")
    r2 = subprocess.run(
        [sys.executable, "scripts/sembrar_demo.py", "--reset"],
        cwd=RAIZ,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0
    test_cantidades_demo(r2.stdout)
