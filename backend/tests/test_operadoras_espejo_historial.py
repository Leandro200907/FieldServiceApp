"""Historial y filtros del espejo por operadora."""
from __future__ import annotations

from sqlalchemy import text

from app.db import tenant_session
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_operadoras_documentales import _registrar


def test_historial_dos_versiones_cinco_pasos_en_orden(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia")
    sujeto = _alta_persona(cliente_api, t, "historial espejo")
    v1 = _cargar(cliente_api, t, sujeto, req, desde="2026-01-01", hasta="2026-06-30")
    _registrar(cliente_api, t, sujeto_id=sujeto, documento_id=v1["documento_id"], estado="enviado",
               exportado_en="2026-01-02T08:00:00Z", enviado_en="2026-01-02T09:00:00Z")
    _registrar(cliente_api, t, sujeto_id=sujeto, documento_id=v1["documento_id"], estado="rechazado",
               rechazado_en="2026-01-03T10:00:00Z")
    _registrar(cliente_api, t, sujeto_id=sujeto, documento_id=v1["documento_id"], estado="enviado",
               enviado_en="2026-01-04T09:00:00Z")
    v2 = _cargar(cliente_api, t, sujeto, req, desde="2026-07-01", hasta="2027-06-30")
    _registrar(cliente_api, t, sujeto_id=sujeto, documento_id=v2["documento_id"], estado="enviado",
               enviado_en="2026-07-02T09:00:00Z")
    _registrar(cliente_api, t, sujeto_id=sujeto, documento_id=v2["documento_id"], estado="aceptado",
               aceptado_en="2026-07-03T11:00:00Z")

    with tenant_session(t.tenant_id) as session:
        operadora_id = session.execute(text(
            "SELECT operadora_id FROM modulo1.operadora_documental WHERE lower(nombre) = lower(:n) LIMIT 1"
        ), {"n": "Operadora Norte"}).scalar_one()
        requisito_id = session.execute(text(
            "SELECT requisito_definicion_id FROM modulo1.documento WHERE documento_id = :d"
        ), {"d": v1["documento_id"]}).scalar_one()

    resp = cliente_api.get(
        "/v1/consultas/historial_operadora",
        headers=t.headers("responsable_legajos"),
        params={"operadora_id": str(operadora_id), "sujeto_id": sujeto, "requisito_definicion_id": str(requisito_id)},
    )
    assert resp.status_code == 200
    versiones = resp.json()["versiones"]
    assert len(versiones) == 2
    pasos = [p["estado"] for v in versiones for p in v["pasos"]]
    assert pasos == ["enviado", "rechazado", "enviado", "enviado", "aceptado"]


def test_filtros_espejo_operadora_y_supervisor(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "VTV", tipo="vehiculo")
    req_p = _alta_def(cliente_api, t, "VTV persona", tipo="persona")
    vehiculo = "vehiculo-espejo-ab123cd"
    persona = _alta_persona(cliente_api, t, "otro sujeto")
    with tenant_session(t.tenant_id) as session:
        apoyo.legajo(session, t.tenant_id, vehiculo, "vehiculo")
        session.execute(text(
            "UPDATE modulo1.legajo SET identificador_natural = 'AB123CD' "
            "WHERE tenant_id = :t AND sujeto_id = :s"
        ), {"t": t.tenant_id, "s": vehiculo})
        apoyo.supervisor_de(session, t, vehiculo)

    doc_v = _cargar(cliente_api, t, vehiculo, req, desde="2026-03-01", hasta="2027-03-01")
    doc_p = _cargar(cliente_api, t, persona, req_p, desde="2026-03-01", hasta="2027-03-01")
    for suj, doc in ((vehiculo, doc_v), (persona, doc_p)):
        _ok(_post(cliente_api, t, "responsable_legajos", "registrar_estado_documento_operadora", {
            "operadora": "YPF",
            "sujeto_id": suj,
            "documento_id": doc["documento_id"],
            "estado": "rechazado",
            "rechazado_en": "2026-03-05T12:00:00Z",
            "fuente_archivo": "estado_operadora.xlsx",
            "fuente_hoja": "Vehículos",
            "fuente_fila": 12,
        }))

    with tenant_session(t.tenant_id) as session:
        ypf = session.execute(text(
            "SELECT operadora_id FROM modulo1.operadora_documental WHERE lower(nombre) = 'ypf'"
        )).scalar_one()

    filtrado = cliente_api.get(
        "/v1/consultas/espejo_operadora",
        headers=t.headers("responsable_legajos"),
        params=[
            ("operadora_id", str(ypf)),
            ("tipo_sujeto", "vehiculo"),
            ("estado_operadora", "rechazado"),
        ],
    )
    assert filtrado.status_code == 200
    body = filtrado.json()
    assert body["total"] == 1
    assert body["items"][0]["identificador_natural"] == "AB123CD"
    assert body["items"][0]["tipo_sujeto"] == "vehiculo"

    with tenant_session(t.tenant_id) as session:
        req_persona = session.execute(text(
            "SELECT requisito_definicion_id FROM modulo1.documento WHERE documento_id = :d"
        ), {"d": doc_p["documento_id"]}).scalar_one()
    ajeno = cliente_api.get(
        "/v1/consultas/historial_operadora",
        headers=t.headers("supervisor"),
        params={
            "operadora_id": str(ypf),
            "sujeto_id": persona,
            "requisito_definicion_id": str(req_persona),
        },
    )
    assert ajeno.status_code == 403

    propio = cliente_api.get(
        "/v1/consultas/espejo_operadora",
        headers=t.headers("supervisor"),
        params=[("tipo_sujeto", "vehiculo")],
    )
    assert propio.status_code == 200
    assert all(i["sujeto_id"] == vehiculo for i in propio.json()["items"])
