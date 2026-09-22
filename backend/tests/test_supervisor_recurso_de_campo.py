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


@pytest.fixture
def escenario_excepcion_propia(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    """El sujeto excepcionable de la evaluación ES el supervisor que la va a operar."""
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    with tenant_session(t.tenant_id) as s:
        esc = armar_escenario(s, t.tenant_id, clasificacion_persona="excepcionable")
        insertar_oc(s, t.tenant_id, "OC-propia", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
        # El sujeto propuesto de la evaluación es el propio supervisor, no persona_0042.
        s.execute(text("DELETE FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = 'persona_0042'"), {"t": t.tenant_id})
        apoyo.legajo(s, t.tenant_id, sujeto)
        # El supervisor tiene además una asignación real sobre sí mismo sería auto-supervisión;
        # en cambio acá se prueba SIN esa asignación: el bloqueo debe ser directo, no depender
        # del universo.
    ev = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion",
               {"commitment_id": "OC-propia", "sujetos_propuestos": [sujeto]})
    assert ev.status_code == 200, ev.text
    return {"t": t, "sujeto": sujeto, "referencia": ev.json()["referencia_evaluacion"], "req": esc["req_apto"]}


def test_supervisor_no_puede_otorgar_excepcion_sobre_si_mismo(cliente_api, escenario_excepcion_propia):
    e = escenario_excepcion_propia
    t, sujeto = e["t"], e["sujeto"]
    h = _headers_de(t, t.usuarios["supervisor"], ["supervisor"], sujeto)
    r = cliente_api.post("/v1/comandos/otorgar_excepcion", json={
        "referencia_evaluacion": e["referencia"], "sujeto_id": sujeto, "requisito_definicion_id": e["req"],
        "commitment_id": "OC-propia", "motivo": "me la doy yo mismo",
    }, headers=h)
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "conflicto_de_interes"


def test_supervisor_no_puede_revocar_excepcion_propia(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    """Un supervisor DISTINTO (con alcance real sobre el titular) otorga la excepción,
    autorizado; el titular no puede revocarla, aunque la excepción sea legítima."""
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    otro = str(uuid.uuid4())
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles) "
                       "VALUES (:u, :t, 'otro3@test', 'otro3', '$2b$12$B6psVF.t.UCDfwi1heqT0unV5R.Sh8F.uf/BP5LXjF4UBmmG.O1U2', ARRAY['supervisor'])"),
                  {"u": otro, "t": t.tenant_id})
        esc = armar_escenario(s, t.tenant_id, clasificacion_persona="excepcionable")
        s.execute(text("DELETE FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = 'persona_0042'"), {"t": t.tenant_id})
        apoyo.legajo(s, t.tenant_id, sujeto)
        insertar_oc(s, t.tenant_id, "OC-rev", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
        apoyo.supervisor_de(s, t, sujeto, supervisor_usuario_id=otro)  # el OTRO supervisor tiene alcance
    ev = _ok(_post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion", {"commitment_id": "OC-rev", "sujetos_propuestos": [sujeto]}))
    h_otro = _headers_de(t, otro, ["supervisor"])
    otorgada = cliente_api.post("/v1/comandos/otorgar_excepcion", json={
        "referencia_evaluacion": ev["referencia_evaluacion"], "sujeto_id": sujeto, "requisito_definicion_id": esc["req_apto"],
        "commitment_id": "OC-rev", "motivo": "otorgada por otro supervisor",
    }, headers=h_otro)
    assert otorgada.status_code == 200, otorgada.text
    h_propio = _headers_de(t, t.usuarios["supervisor"], ["supervisor"], sujeto)
    r = cliente_api.post("/v1/comandos/revocar_excepcion", json={"excepcion_id": otorgada.json()["excepcion_id"]}, headers=h_propio)
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "conflicto_de_interes"


# --------------------------------------------------------------------------- conflicto de interés: autosupervisión


def test_configuracion_no_puede_asignar_supervisor_como_supervisor_de_si_mismo(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    r = _post(cliente_api, t, "configuracion", "asignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": t.usuarios["supervisor"]})
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "conflicto_de_interes"


def test_reasignar_supervisor_a_si_mismo_rechazado(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    """Otro supervisor asigna primero, correctamente; después intentan reasignarlo al
    propio titular, y eso queda bloqueado."""
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    otro = str(uuid.uuid4())
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles) "
                       "VALUES (:u, :t, 'otro@test', 'otro', '$2b$12$B6psVF.t.UCDfwi1heqT0unV5R.Sh8F.uf/BP5LXjF4UBmmG.O1U2', ARRAY['supervisor'])"),
                  {"u": otro, "t": t.tenant_id})
    assert _post(cliente_api, t, "configuracion", "asignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": otro}).status_code == 200
    r = _post(cliente_api, t, "responsable_legajos", "reasignar_supervisor", {"sujeto_id": sujeto, "supervisor_usuario_id": t.usuarios["supervisor"]})
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "conflicto_de_interes"


# --------------------------------------------------------------------------- conflicto de interés: custodia


def test_supervisor_no_puede_asignarse_su_propia_custodia(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, "vehiculo_propio", "vehiculo")
        apoyo.supervisor_de(s, t, sujeto)  # está en su propio universo (autosupervisión ya bloqueada aparte)
    h = _headers_de(t, t.usuarios["supervisor"], ["supervisor"], sujeto)
    r = cliente_api.post("/v1/comandos/cambiar_custodia", json={
        "recurso_id": "vehiculo_propio", "tipo_recurso": "vehiculo", "custodio_id": sujeto, "desde": "2026-09-01",
    }, headers=h)
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "conflicto_de_interes"


def test_responsable_legajos_puede_asignar_custodia_a_un_supervisor(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    """El comando se amplía a responsable_legajos/configuración justamente para este caso:
    otro actor autorizado hace lo que el propio supervisor no puede hacerse."""
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, "vehiculo_propio", "vehiculo")
    r = _post(cliente_api, t, "responsable_legajos", "cambiar_custodia", {
        "recurso_id": "vehiculo_propio", "tipo_recurso": "vehiculo", "custodio_id": sujeto, "desde": "2026-09-01",
    })
    assert r.status_code == 200, r.text

    # El propio supervisor tampoco puede corregir ese período (modificarse su custodia).
    h = _headers_de(t, t.usuarios["supervisor"], ["supervisor"], sujeto)
    r2 = cliente_api.post("/v1/comandos/corregir_custodia", json={"periodo_id": r.json()["periodo_id"], "desde": "2026-09-02"}, headers=h)
    assert r2.status_code == 403 and r2.json()["error"]["codigo"] == "conflicto_de_interes"

    # Pero configuración sí puede corregirlo.
    r3 = _post(cliente_api, t, "configuracion", "corregir_custodia", {"periodo_id": r.json()["periodo_id"], "desde": "2026-09-02"})
    assert r3.status_code == 200, r3.text


def test_otro_supervisor_con_alcance_puede_asignar_custodia(cliente_api, tenant_de_prueba, supervisor_con_legajo):
    """Si el modelo ya permite que OTRO supervisor lo haga (lo tiene en su universo), no
    hace falta escalar a responsable_legajos/configuración."""
    t, sujeto = tenant_de_prueba, supervisor_con_legajo
    otro = str(uuid.uuid4())
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles) "
                       "VALUES (:u, :t, 'otro2@test', 'otro2', '$2b$12$B6psVF.t.UCDfwi1heqT0unV5R.Sh8F.uf/BP5LXjF4UBmmG.O1U2', ARRAY['supervisor'])"),
                  {"u": otro, "t": t.tenant_id})
        apoyo.legajo(s, t.tenant_id, "vehiculo_propio", "vehiculo")
        apoyo.supervisor_de(s, t, sujeto, supervisor_usuario_id=otro)
    h_otro = _headers_de(t, otro, ["supervisor"])
    r = cliente_api.post("/v1/comandos/cambiar_custodia", json={
        "recurso_id": "vehiculo_propio", "tipo_recurso": "vehiculo", "custodio_id": sujeto, "desde": "2026-09-01",
    }, headers=h_otro)
    assert r.status_code == 200, r.text
