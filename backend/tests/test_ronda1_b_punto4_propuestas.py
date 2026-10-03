"""Ronda 1-b punto 4: propuestas pendientes con datos de sujeto y presentación."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _ok, _post


def test_propuestas_pendientes_traen_nombre_y_estado_presentacion(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Propuesta r1b")
    p = _alta_persona(
        cliente_api,
        t,
        "40111222",
        sujeto_id=t.sujeto_tecnico,
        nombre_apellido="Persona Propuesta",
    )
    body = {
        "sujeto_id": p,
        "requisito_definicion_id": req,
        "vigente_desde": "2026-09-01",
        "vigente_hasta": "2027-09-01",
    }
    _ok(_post(cliente_api, t, "tecnico", "proponer_documento", body))
    r = cliente_api.get("/v1/consultas/propuestas_pendientes", headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    prop = next(i for i in items if i["sujeto_id"] == p)
    assert prop["nombre_apellido"] == "Persona Propuesta"
    assert prop["identificador_natural"] == "40111222"
    assert prop["estado_presentacion"] == "propuesta_en_revision"
