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

from app.db import platform_session, tenant_session

RAIZ = Path(__file__).resolve().parents[1]

TENANTS_DEMO = ("patagonia-demo", "anelo-demo", "neuquen-demo")

# Fallas del reporte final que el sembrado admite a propósito (cualquier otra falla el CI).
FALLAS_ESPERADAS_SEMBRADO: frozenset[str] = frozenset()

# Objetivo del guion de demo (por tenant), una vez el sembrador esté corregido.
EVIDENCIAS_PENDIENTES_BANDEJA_POR_TENANT = 1
EVIDENCIAS_INVALIDADAS_POR_TENANT = 1
DOCUMENTOS_LOTE_IMPORTADO_POR_TENANT = 5
DOCUMENTOS_LOTE_REVERTIDO_POR_TENANT = 1
PROPUESTAS_PENDIENTES_MIN_POR_TENANT = 2  # Flujo C: propuestas de tecnico3 (licencia con archivo + ART sin archivo)
ESPEJO_ENTREGAS_MIN_POR_TENANT = 1


def _seccion_notas(stdout: str) -> list[str]:
    marcador = "=== Notas ==="
    if marcador not in stdout:
        pytest.fail(f"La salida del sembrado no incluye {marcador!r}")
    bloque = stdout.split(marcador, 1)[1].split("=== Pasos saltados o con fallas ===", 1)[0]
    notas: list[str] = []
    for linea in bloque.splitlines():
        t = linea.strip()
        if t in ("(ninguna)", ""):
            continue
        if t.startswith("- "):
            notas.append(t[2:].strip())
    return notas


def _seccion_pasos_saltados_o_fallas(stdout: str) -> list[str]:
    marcador = "=== Pasos saltados o con fallas ==="
    if marcador not in stdout:
        pytest.fail(f"La salida del sembrado no incluye {marcador!r}")
    bloque = stdout.split(marcador, 1)[1].split("=== Hallazgos sobre la app ===", 1)[0]
    fallas: list[str] = []
    for linea in bloque.splitlines():
        t = linea.strip()
        if t == "(ninguno)":
            continue
        if t.startswith("[falla]"):
            fallas.append(t[len("[falla]") :].strip())
    return fallas


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
    if nb == "fsm_demo":
        pytest.fail(
            "No ejecutar tests de sembrado contra fsm_demo (demo manual). "
            "Usá modulo1_ci_demo con ENV_FILE dedicado; ver backend/.env.test.example."
        )


@pytest.fixture(scope="module")
def demo_sembrado():
    _exigir_base_demo_tests()
    r = _correr_sembrado("--reset", "--importar-planillas")
    assert r.returncode == 0, r.stderr or r.stdout
    return r.stdout


def test_sembrado_sin_fallas_imprevistas(demo_sembrado):
    """El reporte final del sembrado no debe listar fallas fuera de FALLAS_ESPERADAS_SEMBRADO."""
    _exigir_base_demo_tests()
    fallas = _seccion_pasos_saltados_o_fallas(demo_sembrado)
    inesperadas = [f for f in fallas if f not in FALLAS_ESPERADAS_SEMBRADO]
    assert not inesperadas, "Fallas imprevistas en sembrado:\n" + "\n".join(f"  - {x}" for x in inesperadas)


def test_sembrado_demo_todos_los_legajos_consultables(demo_sembrado, cliente_api):
    """Cada legajo del sembrado demo debe poder abrirse sin error de serialización."""
    _exigir_base_demo_tests()
    password = os.environ.get("DEMO_PASSWORD", "demo-secreto-12")
    for slug in TENANTS_DEMO:
        login = cliente_api.post(
            "/v1/auth/login",
            json={
                "tenant_slug": slug,
                "email": f"responsable_legajos1@{slug}.demo.test",
                "password": password,
            },
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        with platform_session() as ps:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
        assert tid is not None
        with tenant_session(str(tid)) as s:
            sujetos = [row[0] for row in s.execute(text("SELECT sujeto_id FROM modulo1.legajo ORDER BY sujeto_id")).all()]
        assert sujetos, f"{slug}: sin legajos en sembrado"
        for sujeto_id in sujetos:
            r = cliente_api.get(
                "/v1/consultas/legajo",
                params={"sujeto_id": sujeto_id},
                headers=headers,
            )
            assert r.status_code == 200, f"{slug}/{sujeto_id}: {r.status_code} {r.text}"


def test_tecnico1_licencia_por_vencer_y_propuesta_en_revision(demo_sembrado, cliente_api):
    """María González (t1): licencia vigente verificada por vencer + renovación pendiente."""
    _exigir_base_demo_tests()
    from scripts.demo.config import dni_tecnico

    slug = "patagonia-demo"
    password = os.environ.get("DEMO_PASSWORD", "demo-secreto-12")
    login = cliente_api.post(
        "/v1/auth/login",
        json={
            "tenant_slug": slug,
            "email": f"responsable_legajos1@{slug}.demo.test",
            "password": password,
        },
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
        assert tid is not None
        with tenant_session(str(tid)) as s:
            suj = s.execute(
                text(
                    "SELECT sujeto_id FROM modulo1.legajo "
                    "WHERE tenant_id = :t AND identificador_natural = :d"
                ),
                {"t": str(tid), "d": dni_tecnico(slug, 1)},
            ).scalar()
    assert suj
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": str(suj)}, headers=headers)
    assert r.status_code == 200, r.text
    lic = next(d for d in r.json()["documentos"] if d.get("requisito") == "Licencia de conducir")
    assert lic["estado_presentacion"] == "por_vencer"
    assert lic["estado_confirmacion"] == "verificado"
    assert lic.get("propuesta_en_revision") is None
    assert "archivo_en_revision" not in (lic.get("estados_adicionales") or [])


def test_sembrado_separa_notas_de_fallas(demo_sembrado):
    _exigir_base_demo_tests()
    notas = _seccion_notas(demo_sembrado)
    fallas = _seccion_pasos_saltados_o_fallas(demo_sembrado)
    assert any("sin archivo en carga" in n for n in notas)
    assert not [f for f in fallas if f not in FALLAS_ESPERADAS_SEMBRADO]
    bloque_fallas = demo_sembrado.split("=== Pasos saltados o con fallas ===", 1)[1].split(
        "=== Hallazgos sobre la app ===", 1
    )[0]
    assert "(ninguno)" in bloque_fallas


def test_locaciones_demo_nombres_reales(demo_sembrado):
    _exigir_base_demo_tests()
    from app.db import platform_session
    from scripts.demo.config import nombre_locacion_demo

    with platform_session() as ps:
        for slug in TENANTS_DEMO:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            assert tid is not None
            tid = str(tid)
            with tenant_session(tid) as s:
                n_genéricas = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.locacion_oc "
                        "WHERE tenant_id = :t AND nombre LIKE '%Locación %'"
                    ),
                    {"t": tid},
                ).scalar()
                assert n_genéricas == 0, f"{slug}: aún hay locaciones genéricas"
                esperada = nombre_locacion_demo("YPF", 1)
                n = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.locacion_oc "
                        "WHERE tenant_id = :t AND nombre = :n"
                    ),
                    {"t": tid, "n": esperada},
                ).scalar()
                assert n == 1, f"{slug}: falta {esperada}"


def test_presentaciones_con_errores_rechaza_cinco_filas(demo_sembrado):
    """Planilla demo: cinco filas completas, cada una con un único error distinto."""
    _exigir_base_demo_tests()
    from app.db import platform_session
    from app.modules.operadoras import servicio as op_svc
    from app.modules.operadoras.lector_xlsx import leer_planilla
    from scripts.demo.contexto import identidad_de

    slug = "patagonia-demo"
    path = RAIZ / "scripts" / "demo_planillas" / slug / "presentaciones_con_errores.xlsx"
    assert path.is_file(), "correr sembrado con --importar-planillas genera la planilla"
    data = path.read_bytes()
    filas, err_lectura = leer_planilla(data)
    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
        assert tid is not None
        tid = str(tid)
        with tenant_session(tid) as s:
            uid = s.execute(
                text("SELECT usuario_id::text FROM modulo1.usuario WHERE tenant_id = :t AND email = :e"),
                {"t": tid, "e": f"responsable_legajos1@{slug}.demo.test"},
            ).scalar()
            idn = identidad_de(tid, uid, "responsable_legajos")
            resp = op_svc.importar_filas(
                s,
                idn,
                archivo="presentaciones_con_errores.xlsx",
                hoja="Presentaciones",
                filas=filas,
                errores_lectura=err_lectura,
            )
    assert resp["filas_aceptadas"] == 0
    assert resp["filas_rechazadas"] == 5
    por_fila = {e["fila"]: e for e in resp["errores"]}
    assert set(por_fila) == {6, 7, 8, 9, 10}
    assert por_fila[6]["codigo"] == "operadora_inexistente"
    assert "YPF SA" in por_fila[6]["mensaje"]
    assert por_fila[7]["codigo"] == "no_encontrado"
    assert por_fila[8]["codigo"] == "fecha_invalida"
    assert por_fila[9]["codigo"] == "regla_de_dominio"
    assert "Requisito ID inválido" in por_fila[9]["mensaje"]
    assert por_fila[10]["codigo"] == "fila_invalida"


def test_tenant_ids_por_slugs_si_base_no_existe():
    """Sin conectar a una base inexistente no debe explotar (p. ej. reset tras DROP fallido)."""
    from scripts.demo.db_util import tenant_ids_por_slugs

    owner = os.environ.get("DATABASE_URL_MIGRATIONS", "")
    if not owner or "/" not in owner:
        pytest.skip("DATABASE_URL_MIGRATIONS no configurada")
    dsn = owner.replace("postgresql+psycopg://", "postgresql://")
    dsn_inexistente = dsn.rsplit("/", 1)[0] + "/fsm_demo_inexistente_para_test"
    assert tenant_ids_por_slugs(dsn_inexistente, ["patagonia-demo"]) == {}


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
                        "AND estado_version = 'propuesta'"
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


def test_radar_demo_tecnico3_sin_alertas_y_recursos_con_alertas(demo_sembrado):
    """En OC en curso: Lucía (t3) solo alerta por inducción faltante (E-91); recursos con vencidos."""
    _exigir_base_demo_tests()
    from app.comun.paginacion import Pagina
    from app.db import platform_session
    from app.modules.proyeccion import radar as radar_mod
    from scripts.demo.config import dni_tecnico
    from scripts.demo.contexto import identidad_de

    with platform_session() as ps:
        for slug in TENANTS_DEMO:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
            assert tid is not None
            tid = str(tid)
            with tenant_session(tid) as s:
                uid = s.execute(
                    text(
                        "SELECT usuario_id::text FROM modulo1.usuario "
                        "WHERE tenant_id = :t AND email = :e"
                    ),
                    {"t": tid, "e": f"responsable_legajos1@{slug}.demo.test"},
                ).scalar()
                assert uid
                idn = identidad_de(tid, uid, "responsable_legajos")
                oc_id = s.execute(
                    text(
                        "SELECT oc_id::text FROM modulo1.oc "
                        "WHERE tenant_id = :t AND clave_origen = :c"
                    ),
                    {"t": tid, "c": f"OC-{slug}-CURSO"},
                ).scalar()
                assert oc_id, slug
                det = radar_mod.detalle_oc(s, idn, oc_id, Pagina(offset=0, limit=50))
                legajos = [l for g in det["grupos"] for l in g["legajos"]]
                por_tipo = {g["tipo_sujeto"]: g for g in det["grupos"]}
                for tipo in ("empresa", "vehiculo", "equipo"):
                    alertas = [
                        l
                        for l in legajos
                        if l["tipo_sujeto"] == tipo and l["estado_documental"] == "con_alertas_documentales"
                    ]
                    assert alertas, f"{slug}: se esperaba al menos un {tipo} con alertas en {oc_id}"
                dni3 = dni_tecnico(slug, 3)
                t3 = next(
                    (
                        l
                        for l in legajos
                        if l["tipo_sujeto"] == "persona" and l["identificador_natural"] == dni3
                    ),
                    None,
                )
                assert t3, f"{slug}: técnico 3 no está en el radar de la OC en curso"
                if t3["estado_documental"] != "sin_alertas_documentales":
                    leg = radar_mod.detalle_legajo(s, idn, oc_id, t3["sujeto_id"])["legajo"]
                    pendientes = [
                        r["nombre"]
                        for r in leg.get("requisitos", [])
                        if r.get("estado") in ("pendiente_revision", "no_evaluable", "faltante")
                    ]
                    pytest.fail(
                        f"{slug}: técnico 3 debería estar sin alertas, tiene {t3['estado_documental']}; "
                        f"requisitos pendientes: {pendientes}"
                    )
                assert por_tipo["persona"]["total"] >= 3


def test_historial_operadora_rechazo_reenvio_aceptado(demo_sembrado):
    """Tras presentaciones_1 y _2: YPF apto técnico 1 muestra rechazo → enviado → aceptado."""
    _exigir_base_demo_tests()
    from app.db import platform_session
    from app.modules.operadoras import servicio as op_svc
    from scripts.demo.config import dni_tecnico
    from scripts.demo.contexto import identidad_de

    slug = "patagonia-demo"
    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
        assert tid is not None
        tid = str(tid)
        with tenant_session(tid) as s:
            uid = s.execute(
                text("SELECT usuario_id::text FROM modulo1.usuario WHERE tenant_id = :t AND email = :e"),
                {"t": tid, "e": f"responsable_legajos1@{slug}.demo.test"},
            ).scalar()
            assert uid
            idn = identidad_de(tid, uid, "responsable_legajos")
            suj = s.execute(
                text(
                    "SELECT sujeto_id FROM modulo1.legajo "
                    "WHERE tenant_id = :t AND identificador_natural = :d"
                ),
                {"t": tid, "d": dni_tecnico(slug, 1)},
            ).scalar()
            rid = s.execute(
                text(
                    "SELECT requisito_definicion_id::text FROM modulo1.definicion_requisito "
                    "WHERE tenant_id = :t AND nombre = 'Apto médico' LIMIT 1"
                ),
                {"t": tid},
            ).scalar()
            op_id = s.execute(
                text(
                    "SELECT operadora_id::text FROM modulo1.operadora_documental "
                    "WHERE tenant_id = :t AND nombre = 'YPF'"
                ),
                {"t": tid},
            ).scalar()
            assert suj and rid and op_id
            hist = op_svc.historial_operadora(
                s, idn, operadora_id=op_id, sujeto_id=suj, requisito_definicion_id=rid
            )
            assert hist["versiones"], "sin versiones en historial operadora"
            pasos = [p["estado"] for p in hist["versiones"][0]["pasos"]]
            assert "rechazado" in pasos
            assert "enviado" in pasos
            assert "aceptado" in pasos


def test_demo_induccion_competencia_certificado_propio_y_lucia_sin_induccion(demo_sembrado):
    """E-97 en semilla: certificado propio en inducción/competencia; Lucía (t3) sin inducción."""
    _exigir_base_demo_tests()
    from app.db import platform_session
    from scripts.demo.config import dni_tecnico

    slug = "patagonia-demo"
    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
        assert tid is not None
        tid = str(tid)
        with tenant_session(tid) as s:
            suj1 = s.execute(
                text("SELECT sujeto_id FROM modulo1.legajo WHERE tenant_id = :t AND identificador_natural = :d"),
                {"t": tid, "d": dni_tecnico(slug, 1)},
            ).scalar()
            suj3 = s.execute(
                text("SELECT sujeto_id FROM modulo1.legajo WHERE tenant_id = :t AND identificador_natural = :d"),
                {"t": tid, "d": dni_tecnico(slug, 3)},
            ).scalar()
            assert suj1 and suj3
            legado_apto = s.execute(
                text(
                    "SELECT count(*) FROM modulo1.documento_soporte ds "
                    "JOIN modulo1.documento padre ON padre.tenant_id = ds.tenant_id AND padre.documento_id = ds.documento_id "
                    "JOIN modulo1.definicion_requisito r ON r.tenant_id = padre.tenant_id "
                    "AND r.requisito_definicion_id = padre.requisito_definicion_id "
                    "JOIN modulo1.documento sop ON sop.tenant_id = ds.tenant_id AND sop.documento_id = ds.soporte_documento_id "
                    "JOIN modulo1.definicion_requisito rs ON rs.tenant_id = sop.tenant_id "
                    "AND rs.requisito_definicion_id = sop.requisito_definicion_id "
                    "WHERE ds.tenant_id = :t AND r.categoria IN ('induccion', 'competencia') "
                    "AND NOT ds.es_certificado_propio AND rs.nombre = 'Apto médico'"
                ),
                {"t": tid},
            ).scalar()
            assert legado_apto == 0, "inducción/competencia demo no deben usar apto como soporte"
            propios = s.execute(
                text(
                    "SELECT count(*) FROM modulo1.documento_soporte ds "
                    "JOIN modulo1.documento sop ON sop.tenant_id = ds.tenant_id AND sop.documento_id = ds.soporte_documento_id "
                    "JOIN modulo1.documento padre ON padre.tenant_id = ds.tenant_id AND padre.documento_id = ds.documento_id "
                    "JOIN modulo1.definicion_requisito r ON r.tenant_id = padre.tenant_id "
                    "AND r.requisito_definicion_id = padre.requisito_definicion_id "
                    "WHERE ds.tenant_id = :t AND ds.es_certificado_propio AND sop.origen = 'certificado_respaldo' "
                    "AND sop.archivo_validacion = 'valido' AND r.categoria IN ('induccion', 'competencia')"
                ),
                {"t": tid},
            ).scalar()
            assert propios >= 3, "María/Juan/Lucía deben tener respaldo propio válido en inducción/competencia"
            n_ind_t3 = s.execute(
                text(
                    "SELECT count(*) FROM modulo1.documento d "
                    "JOIN modulo1.definicion_requisito r ON r.tenant_id = d.tenant_id "
                    "AND r.requisito_definicion_id = d.requisito_definicion_id "
                    "WHERE d.tenant_id = :t AND d.sujeto_id = :s AND d.estado_version = 'vigente' "
                    "AND r.categoria = 'induccion'"
                ),
                {"t": tid, "s": suj3},
            ).scalar()
            assert n_ind_t3 == 0, "Lucía (t3) debe quedar sin inducción registrada (E-91 demo)"


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
                n_prop_t3 = s.execute(
                    text(
                        "SELECT count(*) FROM modulo1.documento d "
                        "WHERE d.tenant_id = :t AND d.sujeto_id = :s AND d.origen_propuesta "
                        "AND d.estado_confirmacion = 'declarado' AND d.estado_version = 'propuesta'"
                    ),
                    {"t": tid, "s": suj},
                ).scalar()
                assert n_prop_t3 >= 2, f"{slug}: técnico 3 debe tener propuestas demo para la bandeja (otros técnicos)"


def test_reset_idempotente_en_cantidades(demo_sembrado):
    _exigir_base_demo_tests()
    r2 = _correr_sembrado("--reset", "--importar-planillas")
    assert r2.returncode == 0
    test_cantidades_demo(r2.stdout)


def test_reset_cuando_base_no_existe():
    """--reset con la base _demo borrada debe recrearla y sembrar (sin fallar en tenant_ids_por_slugs)."""
    _exigir_base_demo_tests()
    import psycopg

    nb = _nombre_base()
    assert nb
    admin = os.environ.get("DATABASE_URL_ADMIN")
    if not admin:
        pytest.skip("DATABASE_URL_ADMIN requerido para borrar la base demo")
    admin = admin.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (nb,),
        )
        conn.execute(f'DROP DATABASE IF EXISTS "{nb}"')
    r = _correr_sembrado("--reset", "--importar-planillas")
    assert r.returncode == 0, r.stderr or r.stdout
    from app.db import platform_session

    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": "patagonia-demo"}).scalar()
        assert tid is not None


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


def test_database_url_admin_desde_env_file_sin_variable_de_proceso(tmp_path):
    """DATABASE_URL_ADMIN sólo en ENV_FILE: owner sin CREATEDB puede --reset vía admin del archivo."""
    _exigir_base_demo_tests()
    admin = os.environ.get("DATABASE_URL_ADMIN")
    if not admin:
        pytest.skip("DATABASE_URL_ADMIN en el entorno del test (postgres) requerido como valor de referencia")
    env_file = tmp_path / "sembrado.env"
    env_file.write_text(
        "\n".join(
            [
                f"DATABASE_URL={os.environ['DATABASE_URL']}",
                f"DATABASE_URL_MIGRATIONS={os.environ['DATABASE_URL_MIGRATIONS']}",
                f"DATABASE_URL_ADMIN={admin}",
                "DEMO_PASSWORD=demo-secreto-12",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = _env_sembrado(ENV_FILE=str(env_file))
    env.pop("DATABASE_URL_ADMIN", None)
    r = _correr_sembrado("--reset", env=env)
    assert r.returncode == 0, r.stderr or r.stdout


def test_reset_aborta_sin_admin_si_owner_sin_createdb(demo_sembrado, tmp_path):
    """Sin DATABASE_URL_ADMIN el --reset aborta antes de borrar storage ni DROP DATABASE."""
    _exigir_base_demo_tests()
    from app.db import platform_session

    with platform_session() as ps:
        tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": "patagonia-demo"}).scalar()
        assert tid is not None, "requiere demo sembrado previo o fixture module"
        tid_s = str(tid)
    from app.config import settings

    storage_base = Path(settings.storage_local_dir).resolve()
    storage_base.mkdir(parents=True, exist_ok=True)
    marcador = storage_base / tid_s / "no_debe_borrarse_reset_abort.txt"
    marcador.parent.mkdir(parents=True, exist_ok=True)
    marcador.write_text("ok", encoding="utf-8")

    env_file = tmp_path / "sin_admin.env"
    env_file.write_text(
        "\n".join(
            [
                f"DATABASE_URL={os.environ['DATABASE_URL']}",
                f"DATABASE_URL_MIGRATIONS={os.environ['DATABASE_URL_MIGRATIONS']}",
                "DEMO_PASSWORD=demo-secreto-12",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = _env_sembrado(ENV_FILE=str(env_file))
    env.pop("DATABASE_URL_ADMIN", None)

    with platform_session() as ps:
        rev_antes = ps.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert rev_antes

    r = _correr_sembrado("--reset", env=env)
    assert r.returncode == 2, r.stdout
    assert "DATABASE_URL_ADMIN" in (r.stderr or r.stdout)
    assert marcador.is_file(), "storage no debía borrarse al abortar"
    with platform_session() as ps:
        rev_despues = ps.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert rev_despues == rev_antes
        tid_despues = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": "patagonia-demo"}).scalar()
        assert tid_despues is not None
