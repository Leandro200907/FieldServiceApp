"""Revisión de integración y robustez (sesión 4): cadenas de versiones, invariantes de
agregación, aislamiento entre tenants, concurrencia mínima y contrato HTTP.
"""
from __future__ import annotations

import itertools
import threading
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.alcance import ROLES_CON_TODO_DESCARGA, alcance_de_sujetos, sujeto_en_alcance
from app.auth.identidad import Identidad, Rol
from app.core.orquestacion import evaluar_compromiso
from app.db import tenant_session
from app.modules.legajos import esquemas as esq
from app.modules.legajos import servicio as legajos
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _docs, _ok, _post, _vigentes
from tests.test_orquestacion import (
    armar_escenario,
    decidir,
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_excepcion,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    requisitos_de,
    sesion,  # noqa: F401
)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _estados(t, persona, req) -> dict[str, str]:
    return {d["documento_id"]: d["estado_version"] for d in _docs(t, persona, req)}


def _assert_a_lo_sumo_un_vigente(t, persona, req):
    assert len(_vigentes(_docs(t, persona, req))) <= 1


def _proponer(c, t, persona, req, desde, hasta) -> str:
    return _ok(_post(c, t, "tecnico", "proponer_documento", {
        "sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": desde, "vigente_hasta": hasta}))["documento_id"]


def _lote(c, t, persona, req, filas: list[tuple[str, str]]) -> tuple[str, list[str]]:
    lote = str(uuid.uuid4())
    r = _ok(_post(c, t, "responsable_legajos", "importar_lote", {"lote_id": lote, "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": d, "vigente_hasta": h} for d, h in filas]}))
    return lote, [x["documento_id"] for x in r["documentos"]]


# =========================================================================== 3. cadenas A -> B -> C


def test_cadena_rechazo_de_C_con_B_sucedida_restaura_B(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "C-1", t.sujeto_tecnico)
    a = _cargar(cliente_api, t, p, req, desde="2026-01-01", hasta="2026-06-30")["documento_id"]
    b = _cargar(cliente_api, t, p, req, desde="2026-06-01", hasta="2026-12-31")["documento_id"]
    c = _proponer(cliente_api, t, p, req, "2026-12-01", "2027-12-01")
    assert _estados(t, p, req) == {a: "sucedida", b: "sucedida", c: "vigente"}
    r = _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": c}))
    assert r["restaurado_documento_id"] == b
    assert _estados(t, p, req) == {a: "sucedida", b: "vigente", c: "rechazada"}


def test_cadena_revertir_lote_con_B_vigente_restaura_A_y_no_C(cliente_api, tenant_de_prueba):
    """A manual → B por lote (vigente) → revertir: vuelve A. Después C manual sucede a A;
    revertir de nuevo es 409 y nada cambia."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "C-2")
    a = _cargar(cliente_api, t, p, req, desde="2026-01-01", hasta="2026-06-30")["documento_id"]
    lote, (b,) = _lote(cliente_api, t, p, req, [("2026-06-01", "2026-12-31")])
    r = _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote}))
    assert r["documentos_restaurados"] == [a]
    assert _estados(t, p, req) == {a: "vigente", b: "revertida_por_lote"}
    c = _cargar(cliente_api, t, p, req, desde="2026-07-01", hasta="2027-06-30")["documento_id"]
    assert _post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote}).status_code == 409
    assert _estados(t, p, req) == {a: "sucedida", b: "revertida_por_lote", c: "vigente"}


def test_cadena_lote_con_dos_filas_del_mismo_requisito_revierte_ambas_y_restaura_el_manual(cliente_api, tenant_de_prueba):
    """A manual → lote con B y C (C sucede a B dentro del mismo lote) → revertir: B y C
    terminales, la cadena desde C salta B (ya terminal) y restaura A."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "C-3")
    a = _cargar(cliente_api, t, p, req, desde="2026-01-01", hasta="2026-06-30")["documento_id"]
    lote, (b, c) = _lote(cliente_api, t, p, req, [("2026-06-01", "2026-12-31"), ("2026-12-01", "2027-12-31")])
    assert _estados(t, p, req) == {a: "sucedida", b: "sucedida", c: "vigente"}
    r = _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote}))
    assert sorted(r["documentos_revertidos"]) == sorted([b, c]) and r["documentos_restaurados"] == [a]
    assert _estados(t, p, req) == {a: "vigente", b: "revertida_por_lote", c: "revertida_por_lote"}


def test_cadena_rechazo_no_resucita_una_terminal_ni_deja_dos_vigentes(cliente_api, tenant_de_prueba):
    """A (lote) → B propuesta → revertir lote (A terminal, B sigue vigente) → C manual
    (sucede a B) → rechazar B: B ya no está vigente → 409, y sigue un solo vigente (C)."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "C-4", t.sujeto_tecnico)
    lote, (a,) = _lote(cliente_api, t, p, req, [("2026-01-01", "2026-06-30")])
    b = _proponer(cliente_api, t, p, req, "2026-06-01", "2026-12-31")
    _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote}))
    assert _estados(t, p, req) == {a: "revertida_por_lote", b: "vigente"}
    c = _cargar(cliente_api, t, p, req, desde="2026-07-01", hasta="2027-06-30")["documento_id"]
    assert _post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": b}).status_code == 409
    assert _estados(t, p, req) == {a: "revertida_por_lote", b: "sucedida", c: "vigente"}


def test_cadena_sin_antecesor_restaurable_deja_sin_vigente(cliente_api, tenant_de_prueba):
    """Única versión es una propuesta rechazada: no hay nada que restaurar y queda cero
    vigentes (correcto: nunca hubo evidencia aceptada)."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "C-5", t.sujeto_tecnico)
    b = _proponer(cliente_api, t, p, req, "2026-06-01", "2026-12-31")
    r = _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": b}))
    assert r["restaurado_documento_id"] is None
    assert _vigentes(_docs(t, p, req)) == []


def test_cadena_larga_todas_las_combinaciones_mantienen_a_lo_sumo_un_vigente(cliente_api, tenant_de_prueba):
    """Secuencia mixta de 6 operaciones sobre el mismo (sujeto, requisito); tras cada paso
    se verifica la invariante y al final el estado exacto."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "C-6", t.sujeto_tecnico)
    a = _cargar(cliente_api, t, p, req, desde="2026-01-01", hasta="2026-03-31")["documento_id"]; _assert_a_lo_sumo_un_vigente(t, p, req)
    l1, (b,) = _lote(cliente_api, t, p, req, [("2026-03-01", "2026-06-30")]); _assert_a_lo_sumo_un_vigente(t, p, req)
    c = _proponer(cliente_api, t, p, req, "2026-06-01", "2026-09-30"); _assert_a_lo_sumo_un_vigente(t, p, req)
    _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": c})); _assert_a_lo_sumo_un_vigente(t, p, req)
    assert _estados(t, p, req)[b] == "vigente"
    l2, (d,) = _lote(cliente_api, t, p, req, [("2026-09-01", "2026-12-31")]); _assert_a_lo_sumo_un_vigente(t, p, req)
    _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": l1})); _assert_a_lo_sumo_un_vigente(t, p, req)
    # b estaba sucedida por d: se marca terminal sin restaurar; d sigue vigente.
    assert _estados(t, p, req) == {a: "sucedida", b: "revertida_por_lote", c: "rechazada", d: "vigente"}
    _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": l2})); _assert_a_lo_sumo_un_vigente(t, p, req)
    # d vigente → revertida; su antecesor b es terminal → sube a a (sucedida) → a vuelve.
    assert _estados(t, p, req) == {a: "vigente", b: "revertida_por_lote", c: "rechazada", d: "revertida_por_lote"}


# =========================================================================== 4. invariantes de agregación

PERFILES = {
    # nombre: (vigente_hasta del documento, confirmación, con_excepcion)
    "habilitado": (date(2026, 12, 31), "verificado", False),
    "vence": (date(2026, 10, 3), "verificado", False),
    "declarado": (date(2026, 12, 31), "declarado", False),
    "no_hab": (date(2026, 9, 1), "verificado", False),
    "no_hab_exc": (date(2026, 9, 1), "verificado", True),
    "sin_doc": (None, None, False),
}
SEVERIDAD = {"habilitado": 0, "vence_durante_el_trabajo": 1, "requiere_revision": 2, "no_habilitado": 3}


def _armar_persona(s, t, esc, sujeto_id, perfil, commitment_id, referencia):
    hasta, conf, exc = PERFILES[perfil]
    insertar_legajo(s, t, sujeto_id, "persona")
    if hasta:
        insertar_documento(s, t, sujeto_id, esc["req_apto"], date(2026, 1, 1), hasta, conf)
    if exc:
        insertar_excepcion(s, t, referencia, sujeto_id, esc["req_apto"], commitment_id)


@pytest.mark.parametrize("perfil_a,perfil_b", list(itertools.product(PERFILES, PERFILES)))
def test_agregar_un_sujeto_nunca_mejora_ni_vuelve_verde_bajo_excepcion(tenant_de_prueba, sesion, perfil_a, perfil_b):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, "excepcionable")
    sesion.execute(text("DELETE FROM modulo1.legajo WHERE sujeto_id = 'persona_0042'"))
    insertar_oc(sesion, t, "OC-p", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    # una decisión "vacía" no existe: la referencia para las excepciones sale de una
    # decisión sobre la empresa sola no es posible (se exige ≥1 propuesto) → se crea con
    # una persona auxiliar que después se da de baja.
    insertar_legajo(sesion, t, "persona_ref", "persona")
    ref = decidir(sesion, t, "OC-p", AHORA, ["persona_ref"])["referencia_evaluacion"]
    sesion.execute(text("UPDATE modulo1.legajo SET dado_de_baja_en = now() WHERE sujeto_id = 'persona_ref'"))

    _armar_persona(sesion, t, esc, "pA", perfil_a, "OC-p", ref)
    solo_a = evaluar_compromiso(sesion, t, "OC-p", AHORA, None)
    _armar_persona(sesion, t, esc, "pB", perfil_b, "OC-p", ref)
    ambos = evaluar_compromiso(sesion, t, "OC-p", AHORA, None)

    for r in (solo_a, ambos):
        # invariante central 4.1
        if r["resultado_de_decision"] == "puede_asignarse_bajo_excepcion":
            assert r["veredicto_de_cumplimiento"] in ("no_habilitado", "vence_durante_el_trabajo")
        # el global nunca es más favorable que el representante de persona
        rep = next(x for x in r["por_sujeto"] if x["tipo_sujeto"] == "persona" and x["representante"])
        assert SEVERIDAD[r["veredicto_de_cumplimiento"]] >= SEVERIDAD[rep["veredicto"]]
        # puede_asignarse solo si nadie depende de excepción y todos son asignables
        if r["resultado_de_decision"] == "puede_asignarse":
            assert not rep["bajo_excepcion"] and rep["asignable"]
    # agregar B (cualquiera) nunca empeora la asignabilidad ni mejora por encima de lo que B aporta:
    orden = {"puede_asignarse": 0, "puede_asignarse_bajo_excepcion": 1, "no_puede_asignarse": 2}
    assert orden[ambos["resultado_de_decision"]] <= orden[solo_a["resultado_de_decision"]]
    # y el resultado con ambos es el mejor de los individuales (cobertura por "al menos uno")
    solo_b_esperado = {  # asignabilidad de B sola
        "habilitado": 0, "vence": 2, "declarado": 2, "no_hab": 2, "no_hab_exc": 1, "sin_doc": 2}[perfil_b]
    assert orden[ambos["resultado_de_decision"]] == min(orden[solo_a["resultado_de_decision"]], solo_b_esperado)


def test_no_bloqueante_en_ejecucion_advierte_sin_bloquear_pero_otro_requisito_si_bloquea(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, "bloqueante_duro")
    sesion.execute(text("UPDATE modulo1.linea_requisito SET bloqueante_durante_ejecucion = false WHERE requisito_definicion_id = :r"),
                   {"r": esc["req_apto"]})
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 10, 3))
    insertar_oc(sesion, t, "OC-w", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-w", AHORA, None)
    assert (r["veredicto_de_cumplimiento"], r["resultado_de_decision"]) == ("vence_durante_el_trabajo", "puede_asignarse")
    # el mismo sujeto con un segundo requisito bloqueante que vence: ahora sí bloquea
    req2 = insertar_definicion(sesion, t, "Licencia", "persona")
    sesion.execute(text("INSERT INTO modulo1.linea_requisito (matriz_version_id, requisito_definicion_id, tenant_id, clasificacion, "
                        "bloqueante_durante_ejecucion) VALUES (:m, :r, :t, 'bloqueante_duro', true)"), {"m": esc["matriz_id"], "r": req2, "t": t})
    insertar_documento(sesion, t, "persona_0042", req2, date(2026, 1, 1), date(2026, 10, 3))
    r2 = evaluar_compromiso(sesion, t, "OC-w", AHORA, None)
    assert (r2["veredicto_de_cumplimiento"], r2["resultado_de_decision"]) == ("vence_durante_el_trabajo", "no_puede_asignarse")
    reqs = requisitos_de(r2, "persona_0042")
    assert reqs[esc["req_apto"]]["asignable"] is True and reqs[req2]["asignable"] is False


@pytest.mark.parametrize("con_excepcion_empresa", [False, True])
def test_empresa_sin_legajo_nunca_permite_asignar(tenant_de_prueba, sesion, con_excepcion_empresa):
    t = tenant_de_prueba.tenant_id
    clave = clave_de_matriz()
    insertar_legajo(sesion, t, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t, "ART", "empresa")
    req_p = insertar_definicion(sesion, t, "Apto", "persona")
    insertar_matriz(sesion, t, clave, {req_e: "excepcionable", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t, "persona_0042", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t, "OC-e", clave, date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-e", AHORA, None)
    if con_excepcion_empresa:
        # ni siquiera una excepción "para la empresa" sirve si no hay legajo que evaluar
        ref = decidir(sesion, t, "OC-e", AHORA, ["persona_0042"])["referencia_evaluacion"]
        insertar_excepcion(sesion, t, ref, "empresa_fantasma", req_e, "OC-e")
        r = evaluar_compromiso(sesion, t, "OC-e", AHORA, None)
    assert r["resultado_de_decision"] == "no_puede_asignarse"
    assert r["veredicto_de_cumplimiento"] == "no_habilitado"


@pytest.mark.parametrize("periodo_desde,version_esperada", [
    (date(2026, 9, 29), 1), (date(2026, 9, 30), 1), (date(2026, 10, 1), 2), (date(2026, 10, 2), 2),
])
def test_matriz_exacta_en_periodo_desde_bordes_inclusive(tenant_de_prueba, sesion, periodo_desde, version_esperada):
    t = tenant_de_prueba.tenant_id
    clave = clave_de_matriz()
    insertar_legajo(sesion, t, "empresa_0001", "empresa")
    insertar_legajo(sesion, t, "persona_0042", "persona")
    req = insertar_definicion(sesion, t, "Apto", "persona")
    insertar_matriz(sesion, t, clave, {req: "excepcionable"}, version=1, vigente_desde=date(2026, 1, 1), vigente_hasta=date(2026, 9, 30))
    insertar_matriz(sesion, t, clave, {req: "bloqueante_duro"}, version=2, vigente_desde=date(2026, 10, 1))
    insertar_oc(sesion, t, "OC-b", clave, periodo_desde, periodo_desde)
    # evaluada mucho después, y también mucho antes: el resultado no depende de "hoy"
    for ahora in (datetime(2026, 12, 1, tzinfo=timezone.utc), datetime(2026, 6, 1, tzinfo=timezone.utc)):
        r = evaluar_compromiso(sesion, t, "OC-b", ahora, None)
        assert r["version_matriz"]["version"] == version_esperada
        clasif = requisitos_de(r, "persona_0042")[req]["clasificacion"]
        assert clasif == ("excepcionable" if version_esperada == 1 else "bloqueante_duro")


def test_oc_anterior_a_toda_matriz_no_se_evalua(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    clave = clave_de_matriz()
    insertar_legajo(sesion, t, "persona_0042", "persona")
    req = insertar_definicion(sesion, t, "Apto", "persona")
    insertar_matriz(sesion, t, clave, {req: "excepcionable"}, vigente_desde=date(2026, 10, 1))
    insertar_oc(sesion, t, "OC-antes", clave, date(2026, 9, 30), date(2026, 10, 5))
    with pytest.raises(ErrorDeDominio):
        evaluar_compromiso(sesion, t, "OC-antes", datetime(2026, 12, 1, tzinfo=timezone.utc), None)


# =========================================================================== 5. aislamiento entre tenants


def _armar_tenant(c, t) -> dict:
    req = _alta_def(c, t, "Apto")
    persona = _alta_persona(c, t, f"DNI-{t.slug}", t.sujeto_tecnico)
    doc = _cargar(c, t, persona, req, hasta="2026-12-31")["documento_id"]
    clave = {"cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()), "tipo_servicio_id": str(uuid.uuid4())}
    _ok(_post(c, t, "configuracion", "publicar_version_de_matriz", {**clave, "vigente_desde": "2026-01-01", "lineas": [
        {"requisito_definicion_id": req, "clasificacion": "excepcionable", "bloqueante_durante_ejecucion": True}]}))
    _ok(_post(c, t, "responsable_legajos", "importar_lote_oc", {"lote_id": str(uuid.uuid4()), "origen": "planilla", "filas": [
        {"clave_origen": f"OC-{t.slug}", **clave, "vigencia_desde": "2026-10-01", "vigencia_hasta": "2026-10-05"}]}))
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.documento SET clave_storage = :k, archivo_estado = 'confirmado', "
                       "checksum_archivo = 'ck', archivo_bytes = 1 WHERE documento_id = :d"),
                  {"k": f"{t.tenant_id}/{doc}/apto.pdf", "d": doc})
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                       "VALUES (:t, :sj, :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "sj": persona, "u": t.usuarios["supervisor"]})
    return {"req": req, "persona": persona, "doc": doc, "oc": f"OC-{t.slug}"}


def test_aislamiento_por_http_e_interno_entre_dos_tenants(cliente_api, dos_tenants):
    c = cliente_api
    ta, tb = dos_tenants
    a, b = _armar_tenant(c, ta), _armar_tenant(c, tb)

    # --- HTTP: el tenant B intenta leer/escribir cosas del tenant A con sus propios tokens
    assert c.get("/v1/consultas/legajo", params={"sujeto_id": a["persona"]}, headers=tb.headers("responsable_legajos")).status_code == 404
    assert c.get("/v1/consultas/cobertura_oc", params={"commitment_id": a["oc"]}, headers=tb.headers("supervisor")).status_code == 404
    assert c.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": a["oc"], "sujetos_propuestos": [a["persona"]]}, headers=tb.headers("responsable_legajos")).status_code == 404
    assert c.post("/v1/comandos/confirmar_documento", json={"documento_id": a["doc"]}, headers=tb.headers("responsable_legajos")).status_code == 404
    assert c.post("/v1/comandos/cargar_documento", json={"sujeto_id": a["persona"], "requisito_definicion_id": a["req"],
                  "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"}, headers=tb.headers("responsable_legajos")).status_code == 404
    assert c.get(f"/v1/storage/documentos/{a['doc']}/url", headers=tb.headers("responsable_legajos")).status_code == 404
    # listados: B ve solo lo suyo
    tab = _ok(c.get("/v1/consultas/tablero_vencimientos", params={"dias": 365}, headers=tb.headers("responsable_legajos")))
    assert {i["sujeto_id"] for i in tab["items"]} == {b["persona"]}
    back = _ok(c.get("/v1/consultas/backlog_oc", headers=tb.headers("responsable_legajos")))
    assert {i["clave_origen"] for i in back["items"]} == {b["oc"]}
    log = _ok(c.get("/v1/consultas/log_auditoria", params={"limit": 500}, headers=tb.headers("configuracion")))
    assert all(a["persona"] not in str(e) and a["doc"] not in str(e) for e in log["items"])
    # el sujeto de A existe para A
    assert c.get("/v1/consultas/legajo", params={"sujeto_id": a["persona"]}, headers=ta.headers("responsable_legajos")).status_code == 200

    # --- interno: servicios con la sesión de B no ven filas de A aunque conozcan los ids
    with tenant_session(tb.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.documento WHERE documento_id = :d"), {"d": a["doc"]}).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM modulo1.oc WHERE clave_origen = :c"), {"c": a["oc"]}).scalar() == 0
        with pytest.raises(NoEncontrado):
            evaluar_compromiso(s, tb.tenant_id, a["oc"], AHORA, None)
        ident_b = Identidad(tb.tenant_id, tb.usuarios["responsable_legajos"], frozenset({Rol.RESPONSABLE_LEGAJOS}))
        with pytest.raises(NoEncontrado):
            legajos.confirmar_documento(s, ident_b, esq.ConfirmarDocumento(documento_id=a["doc"]))
        # UPDATE "a ciegas" contra una fila ajena no toca nada
        assert s.execute(text("UPDATE modulo1.documento SET numero = 'x' WHERE documento_id = :d"), {"d": a["doc"]}).rowcount == 0
        # ni un INSERT con tenant_id ajeno
        with pytest.raises(Exception):
            s.execute(text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) "
                           "VALUES (:t, 'intruso', 'persona', 'x')"), {"t": ta.tenant_id})
    with tenant_session(ta.tenant_id) as s:
        assert s.execute(text("SELECT numero FROM modulo1.documento WHERE documento_id = :d"), {"d": a["doc"]}).scalar() is None
        assert s.execute(text("SELECT count(*) FROM modulo1.legajo WHERE sujeto_id = 'intruso'")).scalar() == 0

    # --- alcance: el universo de un supervisor de B nunca incluye sujetos de A, ni con
    #     una asignación "plantada" con su usuario_id dentro del tenant A.
    with tenant_session(ta.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                       "VALUES (:t, 'persona_extra_de_A', :u, '2026-01-01', 'test')"), {"t": ta.tenant_id, "u": tb.usuarios["supervisor"]})
    sup_b = Identidad(tb.tenant_id, tb.usuarios["supervisor"], frozenset({Rol.SUPERVISOR}))
    with tenant_session(tb.tenant_id) as s:
        assert alcance_de_sujetos(s, sup_b, date(2026, 9, 18)) == [b["persona"]]
        assert not sujeto_en_alcance(s, sup_b, "persona_extra_de_A", date(2026, 9, 18), ROLES_CON_TODO_DESCARGA)
        assert not sujeto_en_alcance(s, sup_b, a["persona"], date(2026, 9, 18), ROLES_CON_TODO_DESCARGA)
    assert c.get(f"/v1/storage/documentos/{a['doc']}/url", headers=tb.headers("supervisor")).status_code == 404

    # --- storage: una URL firmada del tenant A no la puede usar B (firma atada al tenant)
    url_a = _ok(c.get(f"/v1/storage/documentos/{a['doc']}/url", headers=ta.headers("responsable_legajos")))["url"]
    assert c.get(url_a, headers=tb.headers("responsable_legajos")).status_code == 403

    # --- token de A con tenant_id manipulado hacia B: la firma no valida → 401
    import jwt as pyjwt
    from app.config import settings
    claims = pyjwt.decode(ta.token("responsable_legajos"), options={"verify_signature": False})
    claims["tenant_id"] = tb.tenant_id
    falso = pyjwt.encode(claims, "otro-secreto", algorithm=settings.jwt_algorithm)
    assert c.get("/v1/auth/yo", headers={"Authorization": f"Bearer {falso}"}).status_code == 401


# =========================================================================== 6. concurrencia mínima


def _en_paralelo(fns):
    """Corre las funciones en hilos, arrancando juntas; devuelve [(resultado, excepción)]."""
    barrera = threading.Barrier(len(fns))
    salidas: list = [None] * len(fns)

    def run(i, fn):
        barrera.wait()
        try:
            salidas[i] = (fn(), None)
        except Exception as exc:  # noqa: BLE001
            salidas[i] = (None, exc)

    hilos = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(fns)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    return salidas


def _ident(t, rol) -> Identidad:
    return Identidad(t.tenant_id, t.usuarios[rol], frozenset({Rol(rol)}), t.sujeto_tecnico if rol == "tecnico" else None)


def _cargar_en_sesion(t, persona, req, desde, hasta):
    def fn():
        with tenant_session(t.tenant_id) as s:
            return legajos.cargar_documento(s, _ident(t, "responsable_legajos"), esq.CargarDocumento(
                sujeto_id=persona, requisito_definicion_id=req, vigente_desde=desde, vigente_hasta=hasta))
    return fn


def test_concurrencia_dos_versiones_nuevas_a_la_vez_quedan_serializadas(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "K-1")
    # sin vigente previo (primer documento) y con vigente previo: ambos casos
    for _ in range(2):
        salidas = _en_paralelo([_cargar_en_sesion(t, p, req, date(2026, 1, 1), date(2026, 6, 30)),
                                _cargar_en_sesion(t, p, req, date(2026, 6, 1), date(2026, 12, 31))])
        assert all(exc is None for _, exc in salidas), [str(e) for _, e in salidas if e]
        _assert_a_lo_sumo_un_vigente(t, p, req)
    versiones = sorted(d["version"] for d in _docs(t, p, req))
    assert versiones == [1, 2, 3, 4] and len(_vigentes(_docs(t, p, req))) == 1


def test_concurrencia_confirmar_y_rechazar_la_misma_propuesta(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "K-2", t.sujeto_tecnico)
    _cargar(cliente_api, t, p, req, hasta="2026-06-30")
    prop = _proponer(cliente_api, t, p, req, "2026-06-01", "2026-12-31")

    def confirmar():
        with tenant_session(t.tenant_id) as s:
            return legajos.confirmar_documento(s, _ident(t, "responsable_legajos"), esq.ConfirmarDocumento(documento_id=prop))

    def rechazar():
        with tenant_session(t.tenant_id) as s:
            return legajos.rechazar_propuesta(s, _ident(t, "responsable_legajos"), esq.RechazarPropuesta(documento_id=prop))

    salidas = _en_paralelo([confirmar, rechazar])
    exitos = [r for r, e in salidas if e is None]
    fallos = [e for _, e in salidas if e is not None]
    assert len(exitos) == 1 and len(fallos) == 1 and isinstance(fallos[0], Conflicto)
    _assert_a_lo_sumo_un_vigente(t, p, req)
    estado = _estados(t, p, req)[prop]
    assert estado in ("vigente", "rechazada")


def test_concurrencia_revertir_lote_contra_carga_manual(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p = _alta_persona(cliente_api, t, "K-3")
    a = _cargar(cliente_api, t, p, req, hasta="2026-06-30")["documento_id"]
    lote, (b,) = _lote(cliente_api, t, p, req, [("2026-06-01", "2026-12-31")])

    def revertir():
        with tenant_session(t.tenant_id) as s:
            return legajos.revertir_lote(s, _ident(t, "responsable_legajos"), esq.RevertirLote(lote_id=lote))

    salidas = _en_paralelo([revertir, _cargar_en_sesion(t, p, req, date(2026, 7, 1), date(2027, 6, 30))])
    assert all(e is None for _, e in salidas), [str(e) for _, e in salidas if e]
    estados = _estados(t, p, req)
    c = next(i for i in estados if i not in (a, b))
    assert estados[b] == "revertida_por_lote" and estados[c] == "vigente" and estados[a] == "sucedida"
    _assert_a_lo_sumo_un_vigente(t, p, req)


def test_concurrencia_dos_primeras_asignaciones_de_supervisor(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    p = _alta_persona(cliente_api, t, "K-4")

    def asignar():
        with tenant_session(t.tenant_id) as s:
            return legajos.asignar_supervisor(s, _ident(t, "responsable_legajos"), esq.AsignarSupervisor(
                sujeto_id=p, supervisor_usuario_id=t.usuarios["supervisor"], desde=date(2026, 9, 1)))

    salidas = _en_paralelo([asignar, asignar])
    assert sorted(type(e).__name__ if e else "ok" for _, e in salidas) == ["Conflicto", "ok"]


def test_concurrencia_dos_evaluaciones_de_la_misma_oc_son_dos_filas_consistentes(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t)
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t, "OC-c", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()

    def evaluar():
        with tenant_session(t) as s:
            return decidir(s, t, "OC-c", AHORA, ["persona_0042"])

    salidas = _en_paralelo([evaluar, evaluar])
    assert all(e is None for _, e in salidas)
    refs = {r["referencia_evaluacion"] for r, _ in salidas}
    assert len(refs) == 2 and {r["resultado_de_decision"] for r, _ in salidas} == {"puede_asignarse"}


def test_integrity_error_no_es_500_sino_409(cliente_api, tenant_de_prueba, monkeypatch):
    """Red de seguridad del handler global: una restricción de la base no anticipada
    (carrera) responde 409 con envelope, nunca 500."""
    from app.modules.legajos import infra

    def explota(*_a, **_k):
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key value violates unique constraint"))

    monkeypatch.setattr(infra, "ejecutar_idempotente", explota)
    r = cliente_api.post("/v1/comandos/alta_de_sujeto", json={"tipo_sujeto": "persona", "identificador_natural": "x"},
                         headers=tenant_de_prueba.headers("responsable_legajos"))
    assert r.status_code == 409 and r.json()["error"]["codigo"] == "conflicto_concurrencia"


# =========================================================================== 7. contrato HTTP


def test_contrato_http_codigos_y_serializacion(cliente_api, tenant_de_prueba):
    c, t = cliente_api, tenant_de_prueba
    h = t.headers("responsable_legajos")
    # 401 sin token / 403 rol incorrecto / 422 validación / 404 no encontrado / 409 conflicto — mismo envelope
    casos = [
        (c.post("/v1/comandos/alta_de_sujeto", json={}), 401, "no_autenticado"),
        (c.post("/v1/comandos/otorgar_excepcion", json={"referencia_evaluacion": str(uuid.uuid4()), "sujeto_id": "x",
                "requisito_definicion_id": str(uuid.uuid4()), "commitment_id": "x", "motivo": "x"}, headers=h), 403, "prohibido"),
        # la validación del body corre antes que la autorización: body inválido + rol incorrecto = 422
        (c.post("/v1/comandos/otorgar_excepcion", json={}, headers=h), 422, "validacion"),
        (c.post("/v1/comandos/alta_de_sujeto", json={"tipo_sujeto": "marciano", "identificador_natural": "x"}, headers=h), 422, "validacion"),
        (c.post("/v1/comandos/confirmar_documento", json={"documento_id": str(uuid.uuid4())}, headers=h), 404, "no_encontrado"),
        (c.get("/v1/consultas/legajo", params={"sujeto_id": "nadie"}, headers=h), 404, "no_encontrado"),
        (c.post("/v1/comandos/revertir_lote", json={"lote_id": str(uuid.uuid4())}, headers=h), 404, "no_encontrado"),
    ]
    for r, status, codigo in casos:
        assert r.status_code == status, (r.request.url, r.status_code, r.text)
        cuerpo = r.json()
        assert set(cuerpo) == {"error"} and set(cuerpo["error"]) == {"codigo", "mensaje", "detalles"}
        assert cuerpo["error"]["codigo"] == codigo
    # 409 de dominio y detalles con date/UUID serializados (no 500)
    req = _alta_def(c, t, "Apto")
    p = _alta_persona(c, t, "H-1")
    r = c.post("/v1/comandos/alta_de_sujeto", json={"tipo_sujeto": "persona", "identificador_natural": "H-1"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["codigo"] == "conflicto"
    _cargar(c, t, p, req, hasta="2026-06-30")
    r = c.post("/v1/comandos/cargar_documento", json={"sujeto_id": p, "requisito_definicion_id": req,
               "vigente_desde": "2026-12-31", "vigente_hasta": "2026-01-01"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["detalles"] is not None
    # respuestas OK: UUID/date/enum como strings JSON planos
    leg = _ok(c.get("/v1/consultas/legajo", params={"sujeto_id": p}, headers=h))
    doc = leg["documentos"][0]
    assert isinstance(doc["id"], str) and uuid.UUID(doc["id"]) and doc["tipo"] == "documento"
    assert date.fromisoformat(doc["vigente_hasta"]) == date(2026, 6, 30)
    assert doc["estado_confirmacion"] == "verificado"


def test_contrato_http_todas_las_rutas_estan_protegidas(cliente_api):
    """Cada ruta bajo /v1 (salvo salud, login/refresh y la URL prefirmada de storage) exige
    token: sin Authorization responde 401 con envelope, nunca 500 ni 200."""
    paths = cliente_api.get("/openapi.json").json()["paths"]
    publicas = {"/v1/salud", "/v1/auth/login", "/v1/auth/refresh", "/v1/storage/{firma}"}
    assert len(paths) == 45
    for path, ops in paths.items():
        if path in publicas:
            continue
        for metodo in ops:
            url = path.replace("{documento_id}", str(uuid.uuid4()))
            r = cliente_api.post(url, json={}) if metodo == "post" else getattr(cliente_api, metodo)(url)
            assert r.status_code == 401, (metodo, path, r.status_code)
            assert r.json()["error"]["codigo"] == "no_autenticado"
