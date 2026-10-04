"""E-20: propuesta en estado_version propuesta sin suceder al vigente confirmado."""
from __future__ import annotations

from sqlalchemy import text

from tests import apoyo

from app.db import tenant_session
from app.modules.legajos.servicio import MOTIVO_REEMPLAZO_PROPUESTA
from tests.test_comandos_legajos import (
    _alta_def,
    _alta_persona,
    _cargar,
    _confirmar_con_respaldo,
    _docs,
    _ok,
    _post,
    _vigentes,
)


def _propuestas(docs: list[dict]) -> list[str]:
    return [d["documento_id"] for d in docs if d["estado_version"] == "propuesta"]


def test_e20_flujo_confirmacion_mantiene_vigente_y_luego_sucede(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia E20")
    persona = _alta_persona(cliente_api, t, "DNI-E20-1", t.sujeto_tecnico)
    v1 = _cargar(cliente_api, t, persona, req, hasta="2026-10-23")["documento_id"]

    prop = _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2026-03-17",
                "vigente_hasta": "2027-01-31",
            },
        )
    )
    docs = _docs(t, persona, req)
    assert _vigentes(docs) == [v1]
    assert _propuestas(docs) == [prop["documento_id"]]
    assert prop["estado_version"] == "propuesta"
    assert prop["sucede_a"] == v1

    legajo = cliente_api.get(
        "/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("responsable_legajos")
    ).json()
    doc_leg = next(d for d in legajo["documentos"] if d["requisito_definicion_id"] == req)
    assert doc_leg["id"] == v1
    assert doc_leg.get("propuesta_en_revision") is not None

    with tenant_session(t.tenant_id) as s:
        apoyo.respaldo_valido_en_documento(s, t.tenant_id, prop["documento_id"])
        apoyo.registrar_apertura_archivo(s, t.tenant_id, prop["documento_id"], t.usuarios["responsable_legajos"])
    _ok(_post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": prop["documento_id"]}))

    docs = _docs(t, persona, req)
    assert _vigentes(docs) == [prop["documento_id"]]
    assert next(d for d in docs if d["documento_id"] == v1)["estado_version"] == "sucedida"


def test_e20_rechazo_no_toca_vigente(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia E20 rechazo")
    persona = _alta_persona(cliente_api, t, "DNI-E20-2", t.sujeto_tecnico)
    v1 = _cargar(cliente_api, t, persona, req)["documento_id"]
    prop = _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2026-09-01",
                "vigente_hasta": "2027-09-01",
            },
        )
    )["documento_id"]
    r = _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": prop, "motivo": "no"}))
    assert r["restaurado_documento_id"] is None
    assert _vigentes(_docs(t, persona, req)) == [v1]


def test_e20_segunda_propuesta_reemplaza_la_primera(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia E20 reemplazo")
    persona = _alta_persona(cliente_api, t, "DNI-E20-3", t.sujeto_tecnico)
    _cargar(cliente_api, t, persona, req)
    body = {
        "sujeto_id": persona,
        "requisito_definicion_id": req,
        "vigente_desde": "2026-06-01",
        "vigente_hasta": "2026-12-31",
    }
    p1 = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", body))["documento_id"]
    p2 = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", {**body, "vigente_hasta": "2027-06-30"}))[
        "documento_id"
    ]
    docs = _docs(t, persona, req)
    assert _propuestas(docs) == [p2]
    assert next(d for d in docs if d["documento_id"] == p1)["estado_version"] == "rechazada"
    with tenant_session(t.tenant_id) as s:
        motivo = s.execute(
            text(
                "SELECT payload->>'motivo' FROM modulo1.event_log "
                "WHERE tipo = 'DocumentoRechazado' AND payload->>'documento_id' = :d"
            ),
            {"d": p1},
        ).scalar()
    assert motivo == MOTIVO_REEMPLAZO_PROPUESTA


def test_e20_timeline_no_usa_propuesta_para_tramo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia timeline E20")
    persona = _alta_persona(cliente_api, t, "DNI-E20-TL", t.sujeto_tecnico)
    _cargar(cliente_api, t, persona, req, hasta="2026-10-23")
    _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2026-03-17",
                "vigente_hasta": "2027-01-31",
            },
        )
    )
    r = cliente_api.get(
        "/v1/consultas/timeline_recursos",
        params={"desde": "2026-10-01", "hasta": "2026-11-30", "q": "DNI-E20-TL"},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["sujeto_id"] == persona)
    tramo = next(t for t in item["tramos"] if t["requisito_definicion_id"] == req)
    assert tramo["vigente_hasta"] == "2026-10-23"


def test_e20_propuesta_sin_documento_previo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Carnet E20 solo propuesta")
    persona = _alta_persona(cliente_api, t, "DNI-E20-4", t.sujeto_tecnico)
    prop = _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2026-09-01",
                "vigente_hasta": "2027-09-01",
            },
        )
    )
    assert prop["sucede_a"] is None and prop["estado_version"] == "propuesta"
    assert _vigentes(_docs(t, persona, req)) == []
    rech = _ok(
        _post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": prop["documento_id"], "motivo": "x"})
    )
    assert rech["restaurado_documento_id"] is None
    assert _propuestas(_docs(t, persona, req)) == []
