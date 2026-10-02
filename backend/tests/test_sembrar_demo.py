"""Tests del sembrado demo (requieren Postgres con base *_demo en DATABASE_URL)."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import timedelta
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
PROPUESTAS_PENDIENTES_MIN_POR_TENANT = 3
ESPEJO_ENTREGAS_MIN_POR_TENANT = 1


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


def _env_sembrado(**extra: str) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("DEMO_PASSWORD", "demo-secreto-12")
    env.update(extra)
    return env


def _correr_sembrado(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/sembrar_demo.py", *args],
        cwd=RAIZ,
        env=env or _env_sembrado(),
        capture_output=True,
        text=True,
    )


def _recrear_base_vacia_sin_migraciones() -> None:
    import psycopg

    nb = _nombre_base()
    assert nb
    admin = os.environ.get("DATABASE_URL_ADMIN")
    if not admin:
        pytest.skip("DATABASE_URL_ADMIN requerido para recrear base demo vacía")
    admin = admin.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (nb,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{nb}"')
        conn.execute(f'CREATE DATABASE "{nb}" OWNER modulo1_owner')


def _exigir_base_demo_tests():
    nb = _nombre_base()
    if not nb or not nb.endswith("_demo"):
        pytest.fail("DATABASE_URL debe apuntar a una base que termine en _demo (job Pytest sembrado demo en CI)")


@pytest.fixture(scope="module")
def demo_sembrado():
    _exigir_base_demo_tests()
    r = _correr_sembrado("--reset", "--importar-planillas")
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


def test_propuestas_pendientes_por_tenant(demo_sembrado):
    _exigir_base_demo_tests()
    from app.db import platform_session

    with platform_session() as ps:
        for slug in TENANTS_DEMO:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            assert tid is not None
            tid = str(tid)
            with tenant_session(tid) as s:
                n = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.documento "
                        "WHERE tenant_id = :t AND origen_propuesta AND estado_confirmacion = 'declarado' "
                        "AND estado_version = 'vigente'"
                    ),
                    {"t": tid},
                ).scalar()
                assert n >= PROPUESTAS_PENDIENTES_MIN_POR_TENANT, f"{slug}: propuestas={n}"


def test_espejo_operadora_con_filas_tras_importar(demo_sembrado):
    _exigir_base_demo_tests()
    from app.db import platform_session

    with platform_session() as ps:
        for slug in TENANTS_DEMO:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            assert tid is not None
            tid = str(tid)
            with tenant_session(tid) as s:
                n = s.execute(
                    text("SELECT count(*) FROM modulo1.entrega_documento_operadora WHERE tenant_id = :t"),
                    {"t": tid},
                ).scalar()
                assert n >= ESPEJO_ENTREGAS_MIN_POR_TENANT, f"{slug}: entregas espejo={n}"


def test_tecnico3_todo_vigente(demo_sembrado):
    _exigir_base_demo_tests()
    from app.db import platform_session
    from scripts.demo.config import dni_tecnico
    from scripts.demo.fechas import hoy_tenant

    with platform_session() as ps:
        for slug in TENANTS_DEMO:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            assert tid is not None
            tid = str(tid)
            hoy = hoy_tenant(tid)
            with tenant_session(tid) as s:
                suj = s.execute(
                    text(
                        "SELECT sujeto_id FROM modulo1.legajo "
                        "WHERE tenant_id = :t AND tipo_sujeto = 'persona' "
                        "AND identificador_natural = :d"
                    ),
                    {"t": tid, "d": dni_tecnico(slug, 3)},
                ).scalar()
                assert suj
                vencidos = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.documento d "
                        "JOIN modulo1.definicion_requisito dr "
                        "ON dr.tenant_id = d.tenant_id AND dr.requisito_definicion_id = d.requisito_definicion_id "
                        "WHERE d.tenant_id = :t AND d.sujeto_id = :s AND d.estado_version = 'vigente' "
                        "AND dr.categoria = 'documento' AND d.vigente_hasta < :hoy"
                    ),
                    {"t": tid, "s": suj, "hoy": hoy},
                ).scalar()
                assert vencidos == 0, f"{slug}: documentos vencidos t3={vencidos}"
                pendientes = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.documento d "
                        "JOIN modulo1.definicion_requisito dr "
                        "ON dr.tenant_id = d.tenant_id AND dr.requisito_definicion_id = d.requisito_definicion_id "
                        "WHERE d.tenant_id = :t AND d.sujeto_id = :s AND d.estado_version = 'vigente' "
                        "AND dr.categoria = 'documento' AND dr.nombre = 'Licencia de conducir' "
                        "AND d.vigente_hasta < :limite"
                    ),
                    {"t": tid, "s": suj, "limite": hoy + timedelta(days=45)},
                ).scalar()
                assert pendientes == 0, f"{slug}: licencia t3 no está vigente toda la ventana demo"


def test_reset_idempotente_en_cantidades(demo_sembrado):
    _exigir_base_demo_tests()
    r2 = _correr_sembrado("--reset", "--importar-planillas")
    assert r2.returncode == 0
    test_cantidades_demo(r2.stdout)


def test_reset_sobre_base_vacia_sin_migraciones():
    """--reset debe migrar y sembrar aunque la base exista vacía (sin alembic previo)."""
    _exigir_base_demo_tests()
    _recrear_base_vacia_sin_migraciones()
    r = _correr_sembrado("--reset", "--importar-planillas")
    assert r.returncode == 0, r.stderr or r.stdout
    from app.db import platform_session

    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": "patagonia-demo"}).scalar()
        assert tid is not None
        rev = ps.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert rev


def test_demo_password_leida_desde_env_file(tmp_path):
    _exigir_base_demo_tests()
    pwd = "desde-env-demo-12"
    env_file = tmp_path / "demo.env"
    env_file.write_text(f"DEMO_PASSWORD={pwd}\n", encoding="utf-8")
    env = _env_sembrado(ENV_FILE=str(env_file))
    env.pop("DEMO_PASSWORD", None)
    r = _correr_sembrado("--reset", "--importar-planillas", env=env)
    assert r.returncode == 0, r.stderr or r.stdout
    from app.auth.passwords import verificar_password
    from app.db import platform_session

    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": "patagonia-demo"}).scalar()
        assert tid is not None
    with tenant_session(str(tid)) as s:
        fila = s.execute(
            text(
                "SELECT password_hash FROM modulo1.usuario "
                "WHERE tenant_id = :t AND email = :e"
            ),
            {"t": str(tid), "e": "responsable_legajos1@patagonia-demo.demo.test"},
        ).first()
        assert fila and verificar_password(pwd, fila.password_hash)
