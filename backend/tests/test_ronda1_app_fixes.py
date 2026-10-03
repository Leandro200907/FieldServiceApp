"""Correcciones ronda 1 (fix/app-ronda1-a)."""
from __future__ import annotations

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_operadoras_documentales import _ENCABEZADOS, _alta_operadora, _xlsx


def test_fila_con_contenido_parcial_no_se_omite(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Parcial")
    filas = [
        _ENCABEZADOS,
        ["", "persona", "solo_obs", "", "Apto", "", "", "", "exportado", "", "", "", "nota suelta"],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filas_rechazadas"] >= 1
    assert body["filas_aceptadas"] == 0
    assert any(e["mensaje"] == "Falta la operadora" for e in body["errores"])


def test_errores_importacion_ordenados_por_fila(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Orden")
    req = _alta_def(cliente_api, t, "Apto orden")
    p = _alta_persona(cliente_api, t, "persona_orden")
    _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["   ", "persona", "persona_orden", p, "Apto orden", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
        ["Op Orden", "persona", "persona_orden", p, "Apto orden", req, "",
         "no-es-fecha", "2027-09-25", "exportado", "2026-09-27T11:00:00+00:00", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    body = r.json()
    filas_err = [e["fila"] for e in body["errores"]]
    assert filas_err == sorted(filas_err)
    assert "no es una fecha válida" in body["errores"][-1]["mensaje"]


def test_alta_operadora_solo_configuracion_y_auditoria(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    r_forbidden = cliente_api.post(
        "/v1/comandos/alta_operadora_oc",
        json={"nombre": "Nueva Op"},
        headers=t.headers("responsable_legajos"),
    )
    assert r_forbidden.status_code == 403, r_forbidden.text
    r_ok = cliente_api.post(
        "/v1/comandos/alta_operadora_oc",
        json={"nombre": "Nueva Op"},
        headers=t.headers("configuracion"),
    )
    assert r_ok.status_code == 200, r_ok.text
    with tenant_session(t.tenant_id) as session:
        n = session.execute(
            text(
                "SELECT count(*) FROM modulo1.event_log "
                "WHERE tenant_id = :t AND tipo = 'OperadoraOcCreada' AND payload->>'nombre' = 'Nueva Op'"
            ),
            {"t": t.tenant_id},
        ).scalar()
    assert n == 1


def test_alta_operadora_rechaza_variante_ypf(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    headers = t.headers("configuracion")
    assert cliente_api.post("/v1/comandos/alta_operadora_oc", json={"nombre": "YPF"}, headers=headers).status_code == 200
    r = cliente_api.post("/v1/comandos/alta_operadora_oc", json={"nombre": "YPF SA"}, headers=headers)
    assert r.status_code == 422, r.text
    assert "YPF" in r.json()["error"]["mensaje"]


def test_rechazar_propuesta_exige_motivo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto rechazo")
    p = _alta_persona(cliente_api, t, "persona_rechazo_motivo", sujeto_id=t.sujeto_tecnico)
    body = {"sujeto_id": p, "requisito_definicion_id": req, "vigente_desde": "2026-09-01", "vigente_hasta": "2027-09-01"}
    prop = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", body))
    r_vacio = cliente_api.post(
        "/v1/comandos/rechazar_propuesta",
        json={"documento_id": prop["documento_id"], "motivo": "   "},
        headers=t.headers("responsable_legajos"),
    )
    assert r_vacio.status_code == 422, r_vacio.text
    r_ok = cliente_api.post(
        "/v1/comandos/rechazar_propuesta",
        json={"documento_id": prop["documento_id"], "motivo": "Documento ilegible"},
        headers=t.headers("responsable_legajos"),
    )
    assert r_ok.status_code == 200, r_ok.text
