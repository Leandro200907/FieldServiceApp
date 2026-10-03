"""Propuesta en revisión visible en consultas de legajo (D16 + UI)."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post


def test_legajo_con_propuesta_incluye_propuesta_en_revision(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia propuesta UI")
    persona = _alta_persona(cliente_api, t, "40222333", t.sujeto_tecnico)
    _cargar(cliente_api, t, persona, req, desde="2026-09-01", hasta="2026-12-31")
    _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2027-01-01",
                "vigente_hasta": "2027-01-31",
            },
        )
    )
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    doc = next(d for d in r.json()["documentos"] if d["requisito_definicion_id"] == req)
    assert doc["propuesta_en_revision"] is not None
    assert doc["propuesta_en_revision"]["vigente_hasta"] == "2027-01-31"
    assert doc["estado_presentacion"] in ("verificada", "por_vencer")
