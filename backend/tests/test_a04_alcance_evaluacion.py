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

def test_decision_rechaza_sujeto_de_otro_tenant(dos_tenants):
    ta, tb = dos_tenants
    with tenant_session(ta.tenant_id) as s:
        _escenario(s, ta)
    with tenant_session(tb.tenant_id) as s:
        insertar_legajo(s, tb.tenant_id, "persona_de_B", "persona")
    with tenant_session(ta.tenant_id) as s:
        with pytest.raises(NoEncontrado):
            decidir_habilitacion(s, ta.tenant_id, "OC-1", ["persona_de_B"], AHORA, ta.usuarios["responsable_legajos"])
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
