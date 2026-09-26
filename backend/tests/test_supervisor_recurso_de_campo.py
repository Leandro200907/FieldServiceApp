"""Requisito de dominio nuevo: el Supervisor también puede ser trabajador de campo. El rol
no lo exime del cumplimiento documental — puede vincularse a un legajo de tipo persona,
aparecer como sujeto propuesto en una evaluación, ser evaluado como cualquier otro sujeto,
recibir alertas de sus propios vencimientos y consultar su propio legajo compuesto. Y al
revés: separación de funciones — no puede otorgar/revocar una excepción sobre sí mismo, ni
ser su propio supervisor, ni asignarse/modificarse su propia custodia.

Deliberadamente en un archivo aparte (commit propio): no es parte de H-01..H-06 ni de la
reauditoría congelada, es un requisito de dominio nuevo sobre el mismo modelo."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import text

from app.comun.reloj import hoy_del_tenant
from app.db import tenant_session
from app.worker.procesos_reloj import control_vencimientos
from tests import apoyo
from tests.conftest import token_para
from tests.test_comandos_legajos import _alta_def, _cargar, _ok, _post
from tests.test_orquestacion import armar_escenario, insertar_oc

def _headers_de(t, usuario_id: str, roles: list[str], sujeto_id: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_para(t.tenant_id, usuario_id, roles, sujeto_id)}"}

def _get(cliente_api, t, headers, ruta, **params):
    return cliente_api.get(f"/v1/consultas/{ruta}", params=params, headers=headers)

@pytest.fixture
def supervisor_con_legajo(tenant_de_prueba):
    """El usuario `supervisor` del tenant de prueba, con un legajo de persona vinculado
    (además de su rol). El resto de los tests de custodia/excepciones/alertas ya asumen
    que el `supervisor` de `tenant_de_prueba` NO tiene legajo propio salvo que se use esta
    fixture: no se toca el fixture compartido."""
    t = tenant_de_prueba
    sujeto = f"persona_sup_{t.tenant_id[:8]}"
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, sujeto)
        s.execute(
            text("UPDATE modulo1.usuario SET sujeto_id = :sj WHERE tenant_id = :t AND usuario_id = :u"),
            {"sj": sujeto, "t": t.tenant_id, "u": t.usuarios["supervisor"]},
        )
    return sujeto

# --------------------------------------------------------------------------- alcance propio

def test_supervisor_con_legajo_se_ve_a_si_mismo_en_documentos_y_excepciones(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    req = _alta_def(cliente_api, t, "Apto médico")
    _cargar(cliente_api, t, sujeto, req, hasta="2027-06-30")
    h = _headers_de(t, t.usuarios["supervisor"], ["supervisor"], sujeto)

    r = _get(cliente_api, t, h, "documentos", sujeto_id=sujeto)
    assert r.status_code == 200 and r.json()["total"] == 1
    assert _get(cliente_api, t, h, "legajo", sujeto_id=sujeto).status_code == 200

    # Otra persona, fuera de su universo (sin asignación): sigue fuera de alcance.
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, "persona_otra")
    assert _get(cliente_api, t, h, "legajo", sujeto_id="persona_otra").status_code == 403

def test_supervisor_sin_legajo_no_se_ve_a_si_mismo(cliente_api, tenant_de_prueba):
    """Control negativo: sin `sujeto_id` propio, el universo sigue siendo solo el de
    supervisión asignada — no aparece de la nada."""
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, "persona_ajena")
    assert _get(cliente_api, t, t.headers("supervisor"), "legajo", sujeto_id="persona_ajena").status_code == 403

def test_tecnico_con_rol_supervisor_extra_no_ensancha_su_alcance_tecnico(cliente_api, tenant_de_prueba):
    """Un usuario con roles [tecnico, supervisor] pero SIN asignaciones de supervisión
    sigue viendo solo su propio legajo — el rol adicional no abre nada por sí solo."""
    t = tenant_de_prueba
    persona = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, persona)
        apoyo.legajo(s, t.tenant_id, "persona_otra")
    h = _headers_de(t, t.usuarios["tecnico"], ["tecnico", "supervisor"], persona)
    assert _get(cliente_api, t, h, "legajo", sujeto_id=persona).status_code == 200
    assert _get(cliente_api, t, h, "legajo", sujeto_id="persona_otra").status_code == 403

def test_supervisor_con_doble_rol_acumula_propio_y_universo_asignado_sin_transitividad(cliente_api, tenant_de_prueba):
    """X (técnico + supervisor, legajo propio) supervisa a Y; Y es a su vez supervisor de
    Z. X debe ver: a sí mismo y a Y — nunca a Z (el universo no es transitivo)."""
    t = tenant_de_prueba
    x = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, x)
        apoyo.legajo(s, t.tenant_id, "persona_y")
        apoyo.legajo(s, t.tenant_id, "persona_z")
        # `identidad_actual` revalida roles contra la base (auditoría externa, hallazgo 1):
        # para que el token con ["tecnico", "supervisor"] sea efectivo, la base tiene que
        # tener realmente los dos roles, no solo el JWT.
        s.execute(text("UPDATE modulo1.usuario SET roles = ARRAY['tecnico', 'supervisor'] "
                       "WHERE tenant_id = :t AND usuario_id = :u"), {"t": t.tenant_id, "u": t.usuarios["tecnico"]})
        # X supervisa a Y
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                       "VALUES (:t, 'persona_y', :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "u": t.usuarios["tecnico"]})
        # Y (usuario aparte, con su propio legajo) supervisa a Z
        otro_supervisor = str(uuid.uuid4())
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles, sujeto_id) "
                       "VALUES (:u, :t, 'y@test', 'y', '$2b$12$B6psVF.t.UCDfwi1heqT0unV5R.Sh8F.uf/BP5LXjF4UBmmG.O1U2', ARRAY['supervisor'], 'persona_y')"),
                  {"u": otro_supervisor, "t": t.tenant_id})
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                       "VALUES (:t, 'persona_z', :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "u": otro_supervisor})

    h = _headers_de(t, t.usuarios["tecnico"], ["tecnico", "supervisor"], x)
    lista = _get(cliente_api, t, h, "sujetos").json()
    assert {i["sujeto_id"] for i in lista["items"]} == {x, "persona_y"}
    assert _get(cliente_api, t, h, "legajo", sujeto_id="persona_z").status_code == 403

# --------------------------------------------------------------------------- mi_legajo

def test_supervisor_con_legajo_puede_consultar_mi_legajo(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    req = _alta_def(cliente_api, t, "Apto médico")
    _cargar(cliente_api, t, sujeto, req, hasta="2027-06-30")
    h = _headers_de(t, t.usuarios["supervisor"], ["supervisor"], sujeto)
    r = _get(cliente_api, t, h, "mi_legajo")
    assert r.status_code == 200, r.text
    assert r.json()["persona"]["legajo"]["sujeto_id"] == sujeto

def test_supervisor_sin_legajo_mi_legajo_sigue_prohibido(cliente_api, tenant_de_prueba):
    r = _get(cliente_api, tenant_de_prueba, tenant_de_prueba.headers("supervisor"), "mi_legajo")
    assert r.status_code == 403

# --------------------------------------------------------------------------- alertas propias

def _ahora(d: date) -> datetime:
    return datetime.combine(d, time(15, 0), tzinfo=timezone.utc)

def _mensajes(t) -> list[dict]:
    with tenant_session(t.tenant_id) as s:
        return [dict(f) for f in s.execute(
            text("SELECT payload->>'destinatario_rol' AS destinatario_rol, payload->>'destinatario_usuario_id' AS destinatario_usuario_id "
                 "FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'notificaciones' AND payload->>'tipo' = 'AlertasDeVencimiento' ORDER BY id"),
            {"t": t.tenant_id}).mappings()]

def test_supervisor_recibe_alerta_de_su_propio_vencimiento(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    req = _alta_def(cliente_api, t, "Apto médico")
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)
    vence = hoy + timedelta(days=40)
    _cargar(cliente_api, t, sujeto, req, desde="2026-01-01", hasta=vence.isoformat())

    with tenant_session(t.tenant_id) as s:
        r = control_vencimientos(s, t.tenant_id, _ahora(vence - timedelta(days=30)))
    assert r["abiertas"] == 1

    msgs = _mensajes(t)
    titulares = [m for m in msgs if m["destinatario_rol"] == "tecnico"]
    assert len(titulares) == 1 and titulares[0]["destinatario_usuario_id"] == t.usuarios["supervisor"]

# --------------------------------------------------------------------------- conflicto de interés: excepciones
