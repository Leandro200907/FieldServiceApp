"""Presentación: sin archivo de respaldo vs. archivo en revisión."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post


def test_verificado_sin_archivo_muestra_sin_archivo_respaldo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Doc sin respaldo")
    p = _alta_persona(cliente_api, t, "40123456")
    _cargar(cliente_api, t, p, req, desde="2026-03-01", hasta="2027-03-01")
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": p}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    item = r.json()["documentos"][0]
    assert item["estado_presentacion"] == "verificada"
    assert item["estados_adicionales"] == ["sin_archivo_respaldo"]
    assert item["archivo_validacion"] == "sin_archivo"

