"""A-04 de la auditoría — regla cerrada (ver docs/DECISIONES_DOMINIO.md §7):

- Consulta / cobertura: candidatos = todo el tenant (responsable) o solo el universo del
  supervisor; NUNCA persiste ni emite eventos.
- Decisión: solo responsable de legajos; evalúa EXCLUSIVAMENTE los sujetos propuestos y
  persiste snapshot + relación normalizada + evento en la misma transacción.
- Historial: el supervisor ve una decisión solo si TODOS sus sujetos propuestos están en
  su universo; si uno queda afuera, la decisión completa no existe para él.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.errores import ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.identidad import Identidad, Rol
from app.core.orquestacion import cobertura_de_oc, decidir_habilitacion
from app.db import tenant_session
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    sesion,  # noqa: F401
)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
HOY = date(2026, 9, 18)


def _ident(t, rol: str) -> Identidad:
    return Identidad(t.tenant_id, t.usuarios[rol], frozenset({Rol(rol)}))


def _segundo_supervisor(t) -> str:
    """Un segundo usuario supervisor en el mismo tenant (universo disjunto)."""
    uid = str(uuid.uuid4())
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles) "
                       "VALUES (:u, :t, :e, 'sup2', 'x', ARRAY['supervisor'])"),
                  {"u": uid, "t": t.tenant_id, "e": f"sup2@{t.slug}.test"})
    return uid


def _asignar(s, t, sujeto_id: str, supervisor_usuario_id: str) -> None:
    s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                   "VALUES (:t, :sj, :u, '2026-01-01', 'test')"), {"t": t, "sj": sujeto_id, "u": supervisor_usuario_id})


def _escenario(s, t):
    """Empresa OK; personas A (habilitada, universo sup1), B (habilitada, universo sup2),
    C (sin documento, sin supervisor). Matriz exige apto (persona) y ART (empresa)."""
    clave = clave_de_matriz()
    insertar_legajo(s, t.tenant_id, "empresa_0001", "empresa")
    for p in ("persona_A", "persona_B", "persona_C"):
        insertar_legajo(s, t.tenant_id, p, "persona")
    req_e = insertar_definicion(s, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(s, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(s, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "excepcionable"})
    insertar_documento(s, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(s, t.tenant_id, "persona_A", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(s, t.tenant_id, "persona_B", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(s, t.tenant_id, "OC-1", clave, date(2026, 10, 1), date(2026, 10, 5))
    sup2 = _segundo_supervisor(t)
    _asignar(s, t.tenant_id, "persona_A", t.usuarios["supervisor"])
    _asignar(s, t.tenant_id, "persona_B", sup2)
    return {"clave": clave, "req_p": req_p, "sup2": sup2}


def _contar(s, tabla: str, extra: str = "") -> int:
    return s.execute(text(f"SELECT count(*) FROM modulo1.{tabla} {extra}")).scalar()


# ------------------------------------------------------------------ consulta / cobertura


def test_cobertura_de_supervisor_limitada_a_su_universo_sin_persistir_ni_eventos(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    esc = _escenario(sesion, t)
    sesion.commit()
    # sup1 (universo = persona_A) cubre con A; sup2 (universo = persona_B) cubre con B; ninguno ve al otro
    r1 = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-1"}, headers=t.headers("supervisor")).json()
    assert r1["resultado_de_decision"] == "puede_asignarse"
    assert {x["sujeto_id"] for x in r1["por_sujeto"] if x["tipo_sujeto"] != "empresa"} == {"persona_A"}
    assert "persona_B" not in str(r1) and "persona_C" not in str(r1)
    # el responsable ve todo el tenant y elige el mejor por tipo
    r_resp = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-1"}, headers=t.headers("responsable_legajos")).json()
    assert {x["sujeto_id"] for x in r_resp["por_sujeto"] if x["tipo_sujeto"] != "empresa"} == {"persona_A", "persona_B", "persona_C"}
    # un supervisor sin universo no obtiene cobertura de nadie (y no infiere que existan otros)
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.asignacion_supervisor SET estado = 'cerrada', hasta = '2026-02-01' WHERE supervisor_usuario_id = :u"),
                  {"u": t.usuarios["supervisor"]})
    r_vacio = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-1"}, headers=t.headers("supervisor")).json()
    assert r_vacio["resultado_de_decision"] == "no_puede_asignarse"
    assert [x for x in r_vacio["por_sujeto"] if x["tipo_sujeto"] != "empresa"] == []
    # NADA persistido ni emitido por las consultas
    with tenant_session(t.tenant_id) as s:
        assert _contar(s, "evaluacion_habilitacion") == 0
        assert _contar(s, "evaluacion_sujeto_propuesto") == 0
        assert _contar(s, "event_log", "WHERE tipo = 'EvaluacionDeHabilitacionRealizada'") == 0
        assert _contar(s, "outbox_events") == 0


def test_cobertura_no_reutiliza_una_decision_persistida(cliente_api, tenant_de_prueba, sesion):
    """La cobertura es un barrido en modo consulta: aunque exista una decisión persistida
    con otros sujetos, la cobertura se calcula con los candidatos de quien consulta."""
    t = tenant_de_prueba
    _escenario(sesion, t)
    decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_B"], AHORA, t.usuarios["responsable_legajos"])
    sesion.commit()
    r = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-1"}, headers=t.headers("supervisor")).json()
    assert {x["sujeto_id"] for x in r["por_sujeto"] if x["tipo_sujeto"] != "empresa"} == {"persona_A"}
    assert "referencia_evaluacion" not in r
    with tenant_session(t.tenant_id) as s:
        assert _contar(s, "evaluacion_habilitacion") == 1  # solo la decisión explícita


# ------------------------------------------------------------------ decisión


def test_supervisor_rechazado_en_modo_decision_y_responsable_autorizado(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    _escenario(sesion, t)
    sesion.commit()
    body = {"commitment_id": "OC-1", "sujetos_propuestos": ["persona_A"]}
    r = cliente_api.post("/v1/comandos/evaluar_habilitacion", json=body, headers=t.headers("supervisor"))
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "prohibido"
    with tenant_session(t.tenant_id) as s:
        assert _contar(s, "evaluacion_habilitacion") == 0
    r = cliente_api.post("/v1/comandos/evaluar_habilitacion", json=body, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    ref = r.json()["referencia_evaluacion"]
    with tenant_session(t.tenant_id) as s:
        assert _contar(s, "evaluacion_habilitacion") == 1
        assert s.execute(text("SELECT sujeto_id, tipo_sujeto_al_proponer FROM modulo1.evaluacion_sujeto_propuesto WHERE evaluacion_id = :e"),
                         {"e": ref}).all() == [("persona_A", "persona")]
        assert _contar(s, "event_log", "WHERE tipo = 'EvaluacionDeHabilitacionRealizada'") == 1


def test_decision_se_calcula_solo_con_los_sujetos_propuestos(tenant_de_prueba, sesion):
    """Proponer a C (sin documento) da no_puede_asignarse aunque A y B estén perfectas:
    la decisión no busca "el mejor del tenant", evalúa la cuadrilla propuesta."""
    t = tenant_de_prueba
    _escenario(sesion, t)
    r = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_C"], AHORA, t.usuarios["responsable_legajos"])
    assert r["resultado_de_decision"] == "no_puede_asignarse"
    assert {x["sujeto_id"] for x in r["por_sujeto"]} == {"empresa_0001", "persona_C"}
    r2 = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_A", "persona_C"], AHORA, t.usuarios["responsable_legajos"])
    # todos los propuestos deben ser asignables: se está asignando la cuadrilla entera
    assert r2["resultado_de_decision"] == "no_puede_asignarse"
    r3 = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_A", "persona_B"], AHORA, t.usuarios["responsable_legajos"])
    assert r3["resultado_de_decision"] == "puede_asignarse"
    assert r3["sujetos_propuestos"] == ["persona_A", "persona_B"]


@pytest.mark.parametrize("propuestos,motivo", [
    (["persona_A", "persona_A"], "duplicado"),
    (["persona_inexistente"], "inexistente"),
    (["persona_baja"], "inactivo"),
    (["empresa_0001"], "empresa"),
    ([], "vacio"),
])
def test_decision_rechaza_sujetos_invalidos(tenant_de_prueba, sesion, propuestos, motivo):
    t = tenant_de_prueba
    _escenario(sesion, t)
    insertar_legajo(sesion, t.tenant_id, "persona_baja", "persona")
    sesion.execute(text("UPDATE modulo1.legajo SET dado_de_baja_en = now() WHERE sujeto_id = 'persona_baja'"))
    with pytest.raises((ErrorDeDominio, NoEncontrado)):
        decidir_habilitacion(sesion, t.tenant_id, "OC-1", propuestos, AHORA, None)
    assert _contar(sesion, "evaluacion_habilitacion") == 0


def test_decision_rechaza_sujeto_de_otro_tenant(dos_tenants, cliente_api):
    ta, tb = dos_tenants
    with tenant_session(ta.tenant_id) as s:
        _escenario(s, ta)
    with tenant_session(tb.tenant_id) as s:
        insertar_legajo(s, tb.tenant_id, "persona_de_B", "persona")
    r = cliente_api.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-1", "sujetos_propuestos": ["persona_de_B"]},
                         headers=ta.headers("responsable_legajos"))
    assert r.status_code == 404  # para A, ese legajo no existe
    with tenant_session(ta.tenant_id) as s:
        assert _contar(s, "evaluacion_habilitacion") == 0


def test_relacion_evaluacion_sujeto_no_cruza_tenants(dos_tenants):
    """FK compuesta por tenant: ni con la sesión "correcta" se puede apuntar a una
    evaluación o a un legajo de otro tenant."""
    ta, tb = dos_tenants
    with tenant_session(ta.tenant_id) as s:
        _escenario(s, ta)
        ref_a = decidir_habilitacion(s, ta.tenant_id, "OC-1", ["persona_A"], AHORA, None)["referencia_evaluacion"]
    with tenant_session(tb.tenant_id) as s:
        insertar_legajo(s, tb.tenant_id, "persona_de_B", "persona")
    # desde B: evaluación de A + legajo de B → la FK (tenant_id, evaluacion_id) no existe para B
    with pytest.raises(IntegrityError):
        with tenant_session(tb.tenant_id) as s:
            s.execute(text("INSERT INTO modulo1.evaluacion_sujeto_propuesto (tenant_id, evaluacion_id, sujeto_id, tipo_sujeto_al_proponer) "
                           "VALUES (:t, :e, 'persona_de_B', 'persona')"), {"t": tb.tenant_id, "e": ref_a})
    # desde A: evaluación de A + legajo de B → la FK (tenant_id, sujeto_id) no existe para A
    with pytest.raises(IntegrityError):
        with tenant_session(ta.tenant_id) as s:
            s.execute(text("INSERT INTO modulo1.evaluacion_sujeto_propuesto (tenant_id, evaluacion_id, sujeto_id, tipo_sujeto_al_proponer) "
                           "VALUES (:t, :e, 'persona_de_B', 'persona')"), {"t": ta.tenant_id, "e": ref_a})
    # y con tenant_id ajeno directamente, la policy RLS lo rechaza
    with pytest.raises(Exception):
        with tenant_session(tb.tenant_id) as s:
            s.execute(text("INSERT INTO modulo1.evaluacion_sujeto_propuesto (tenant_id, evaluacion_id, sujeto_id, tipo_sujeto_al_proponer) "
                           "VALUES (:t, :e, 'persona_A', 'persona')"), {"t": ta.tenant_id, "e": ref_a})


# ------------------------------------------------------------------ historial


def test_decision_historica_oculta_por_completo_si_un_sujeto_esta_fuera_del_universo(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    esc = _escenario(sesion, t)
    resp = t.usuarios["responsable_legajos"]
    sesion.commit()
    with tenant_session(t.tenant_id) as s:  # la mixta primero, la de A sola después (última global)
        mixta = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A", "persona_B"], AHORA, resp)["referencia_evaluacion"]
    with tenant_session(t.tenant_id) as s:
        solo_a = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, resp)["referencia_evaluacion"]
    h = t.headers("supervisor")  # universo = persona_A
    # backlog: la última decisión GLOBAL es la de A sola y es visible para sup1
    item = next(i for i in cliente_api.get("/v1/consultas/backlog_oc", headers=h).json()["items"] if i["clave_origen"] == "OC-1")
    assert item["ultima_decision"]["referencia_evaluacion"] == solo_a
    # historial de decisiones de la OC
    hist = cliente_api.get("/v1/consultas/decisiones_oc", params={"commitment_id": "OC-1"}, headers=h).json()
    assert [d["referencia_evaluacion"] for d in hist["items"]] == [solo_a]
    assert "persona_B" not in str(hist)
    # el responsable ve las dos
    hist_r = cliente_api.get("/v1/consultas/decisiones_oc", params={"commitment_id": "OC-1"}, headers=t.headers("responsable_legajos")).json()
    assert {d["referencia_evaluacion"] for d in hist_r["items"]} == {solo_a, mixta}
    # acceso directo a la mixta por id: 404 para sup1 (no debe ni confirmar que existe)
    assert cliente_api.get("/v1/consultas/decision", params={"referencia_evaluacion": mixta}, headers=h).status_code == 404
    assert cliente_api.get("/v1/consultas/decision", params={"referencia_evaluacion": solo_a}, headers=h).status_code == 200
    # la empresa nunca interviene en el cálculo del universo: la decisión "solo A" incluye la
    # fila de empresa en por_sujeto y sigue siendo visible
    d = cliente_api.get("/v1/consultas/decision", params={"referencia_evaluacion": solo_a}, headers=h).json()
    assert {x["tipo_sujeto"] for x in d["por_sujeto"]} == {"empresa", "persona"}


def test_excepcion_del_supervisor_solo_sobre_decisiones_y_sujetos_de_su_universo(cliente_api, tenant_de_prueba, sesion):
    """2.3 §3: el supervisor ve/otorga excepciones que involucren a sus sujetos."""
    t = tenant_de_prueba
    esc = _escenario(sesion, t)
    sesion.execute(text("DELETE FROM modulo1.documento WHERE sujeto_id IN ('persona_A', 'persona_B')"))
    resp = t.usuarios["responsable_legajos"]
    ref_a = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_A"], AHORA, resp)["referencia_evaluacion"]
    ref_b = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_B"], AHORA, resp)["referencia_evaluacion"]
    sesion.commit()
    h = t.headers("supervisor")
    base = {"requisito_definicion_id": esc["req_p"], "commitment_id": "OC-1", "motivo": "regulariza mañana"}
    assert cliente_api.post("/v1/comandos/otorgar_excepcion", json={**base, "referencia_evaluacion": ref_b, "sujeto_id": "persona_B"}, headers=h).status_code == 404
    assert cliente_api.post("/v1/comandos/otorgar_excepcion", json={**base, "referencia_evaluacion": ref_a, "sujeto_id": "persona_B"}, headers=h).status_code == 403
    assert cliente_api.post("/v1/comandos/otorgar_excepcion", json={**base, "referencia_evaluacion": ref_a, "sujeto_id": "persona_A"}, headers=h).status_code == 200


def test_ultima_decision_del_backlog_es_la_global_y_no_se_sustituye_por_una_anterior_visible(cliente_api, tenant_de_prueba, sesion):
    """Decisión 1 (solo A, visible para sup1) y decisión 2 posterior (A+B, B fuera del
    universo de sup1): el backlog de sup1 NO presenta la 1 como última ni revela la 2."""
    t = tenant_de_prueba
    _escenario(sesion, t)
    resp = t.usuarios["responsable_legajos"]
    sesion.commit()
    with tenant_session(t.tenant_id) as s:  # transacciones separadas → creado_en distinto
        d1 = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, resp)["referencia_evaluacion"]
    with tenant_session(t.tenant_id) as s:
        d2 = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A", "persona_B"], AHORA, resp)["referencia_evaluacion"]
    item = next(i for i in cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("supervisor")).json()["items"]
                if i["clave_origen"] == "OC-1")
    assert item["ultima_decision"] is None
    assert d1 not in str(item) and d2 not in str(item) and "persona_B" not in str(item)
    # el responsable ve la 2 como última; el historial de sup1 sigue mostrando solo la 1
    item_r = next(i for i in cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("responsable_legajos")).json()["items"]
                  if i["clave_origen"] == "OC-1")
    assert item_r["ultima_decision"]["referencia_evaluacion"] == d2
    hist = cliente_api.get("/v1/consultas/decisiones_oc", params={"commitment_id": "OC-1"}, headers=t.headers("supervisor")).json()
    assert [d["referencia_evaluacion"] for d in hist["items"]] == [d1]


def test_ningun_supervisor_puede_otorgar_excepcion_sobre_la_empresa(cliente_api, tenant_de_prueba, sesion):
    """Cierre seguro: deshabilitado con error de dominio estable (422), independientemente
    del alcance — ni siquiera con la empresa 'plantada' en el universo del supervisor."""
    t = tenant_de_prueba
    esc = _escenario(sesion, t)
    req_e = sesion.execute(text("SELECT requisito_definicion_id FROM modulo1.definicion_requisito WHERE nombre = 'ART'")).scalar()
    sesion.execute(text("UPDATE modulo1.linea_requisito SET clasificacion = 'excepcionable' WHERE requisito_definicion_id = :r"), {"r": req_e})
    sesion.execute(text("DELETE FROM modulo1.documento WHERE sujeto_id = 'empresa_0001'"))
    ref = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_A"], AHORA, t.usuarios["responsable_legajos"])["referencia_evaluacion"]
    _asignar(sesion, t.tenant_id, "empresa_0001", t.usuarios["supervisor"])  # plantada a propósito
    sesion.commit()
    for rol_sup in (t.usuarios["supervisor"], esc["sup2"]):
        from tests.conftest import token_para
        h = {"Authorization": f"Bearer {token_para(t.tenant_id, rol_sup, ['supervisor'])}"}
        r = cliente_api.post("/v1/comandos/otorgar_excepcion", json={
            "referencia_evaluacion": ref, "sujeto_id": "empresa_0001", "requisito_definicion_id": str(req_e),
            "commitment_id": "OC-1", "motivo": "x"}, headers=h)
        assert r.status_code == 422 and r.json()["error"]["codigo"] == "excepcion_de_empresa_deshabilitada", r.text
    with tenant_session(t.tenant_id) as s:
        assert _contar(s, "excepcion") == 0
