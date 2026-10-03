"""Ronda 1-b punto 2: estado de presentación unificado en consultas de legajo."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post


def test_legajo_expone_estado_presentacion_y_campos(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Doc presentacion r1b")
    p = _alta_persona(cliente_api, t, "persona_pres_r1b", nombre_apellido="Técnico Presentación")
    _cargar(cliente_api, t, p, req, desde="2026-03-01", hasta="2027-03-01")
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": p}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    docs = r.json()["documentos"]
    assert len(docs) == 1
    item = docs[0]
    assert item["estado_presentacion"] == "verificada"
    assert item.get("estados_adicionales") in (
        None,
        ["sin_archivo_respaldo"],
        ["archivo_en_revision"],
        ["declarada"],
        ["declarada", "sin_archivo_respaldo"],
        ["declarada", "archivo_en_revision"],
    )
    assert item["estado_presentacion_explicacion"]
    assert "archivo_validacion" in item
