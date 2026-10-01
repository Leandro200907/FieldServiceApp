"""Tests del sembrado demo (requieren Postgres con base *_demo en DATABASE_URL)."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import tenant_session

RAIZ = Path(__file__).resolve().parents[1]

TENANTS_DEMO = ("patagonia-demo", "anelo-demo", "neuquen-demo")

# Fallas del reporte final que el sembrado admite a propósito (cualquier otra falla el CI).
FALLAS_ESPERADAS_SEMBRADO: frozenset[str] = frozenset()

# Objetivo del guion de demo (por tenant), una vez el sembrador esté corregido.
EVIDENCIAS_PENDIENTES_BANDEJA_POR_TENANT = 2
EVIDENCIAS_INVALIDADAS_POR_TENANT = 1
DOCUMENTOS_LOTE_IMPORTADO_POR_TENANT = 5
DOCUMENTOS_LOTE_REVERTIDO_POR_TENANT = 1


def _seccion_pasos_saltados_o_fallas(stdout: str) -> tuple[list[str], list[str]]:
    marcador = "=== Pasos saltados o con fallas ==="
    if marcador not in stdout:
        pytest.fail(f"La salida del sembrado no incluye {marcador!r}")
    bloque = stdout.split(marcador, 1)[1].split("=== Hallazgos sobre la app ===", 1)[0]
    saltados: list[str] = []
    fallas: list[str] = []
    for linea in bloque.splitlines():
        t = linea.strip()
        if t == "(ninguno)":
            continue
        if t.startswith("[saltado]"):
            saltados.append(t[len("[saltado]") :].strip())
        elif t.startswith("[falla]"):
            fallas.append(t[len("[falla]") :].strip())
    return saltados, fallas


def _lote_id_demo(slug: str, sufijo: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"{sufijo}-{slug}")


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


def test_sembrado_sin_fallas_imprevistas(demo_sembrado):
    """El reporte final del sembrado no debe listar fallas fuera de FALLAS_ESPERADAS_SEMBRADO."""
    _exigir_base_demo_tests()
    _, fallas = _seccion_pasos_saltados_o_fallas(demo_sembrado)
    inesperadas = [f for f in fallas if f not in FALLAS_ESPERADAS_SEMBRADO]
    assert not inesperadas, "Fallas imprevistas en sembrado:\n" + "\n".join(f"  - {x}" for x in inesperadas)


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


def test_evidencias_y_lotes_demo(demo_sembrado):
    _exigir_base_demo_tests()
    from app.db import platform_session

    with platform_session() as ps:
        for slug in TENANTS_DEMO:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            assert tid is not None, slug
            tid = str(tid)
            lote_ok = _lote_id_demo(slug, "lote-doc")
            lote_rev = _lote_id_demo(slug, "lote-rev")
            with tenant_session(tid) as s:
                n_pend = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.documento "
                        "WHERE tenant_id = :t AND archivo_estado = 'confirmado' AND archivo_validacion = 'pendiente'"
                    ),
                    {"t": tid},
                ).scalar()
                n_inv = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.documento "
                        "WHERE tenant_id = :t AND archivo_estado = 'confirmado' AND archivo_validacion = 'invalido'"
                    ),
                    {"t": tid},
                ).scalar()
                assert n_pend == EVIDENCIAS_PENDIENTES_BANDEJA_POR_TENANT, (
                    f"{slug}: pendientes bandeja={n_pend}, esperado {EVIDENCIAS_PENDIENTES_BANDEJA_POR_TENANT}"
                )
                assert n_inv == EVIDENCIAS_INVALIDADAS_POR_TENANT, (
                    f"{slug}: invalidadas={n_inv}, esperado {EVIDENCIAS_INVALIDADAS_POR_TENANT}"
                )
                n_lote_ok = s.execute(
                    text("SELECT count(*) FROM modulo1.documento WHERE tenant_id = :t AND lote_id = :l"),
                    {"t": tid, "l": str(lote_ok)},
                ).scalar()
                assert n_lote_ok == DOCUMENTOS_LOTE_IMPORTADO_POR_TENANT, slug
                estado_rev = s.execute(
                    text(
                        "SELECT estado FROM modulo1.lote_importacion "
                        "WHERE tenant_id = :t AND lote_id = :l AND entidad = 'legajos'"
                    ),
                    {"t": tid, "l": str(lote_rev)},
                ).scalar()
                assert estado_rev == "revertido", slug
                n_rev_docs = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.documento "
                        "WHERE tenant_id = :t AND lote_id = :l AND estado_version = 'revertida_por_lote'"
                    ),
                    {"t": tid, "l": str(lote_rev)},
                ).scalar()
                assert n_rev_docs == DOCUMENTOS_LOTE_REVERTIDO_POR_TENANT, slug


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
