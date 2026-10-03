"""Presentación: sin archivo de respaldo vs. archivo en revisión."""
from __future__ import annotations

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar


def test_verificado_sin_archivo_muestra_sin_archivo_respaldo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Doc sin respaldo")
    p = _alta_persona(cliente_api, t, "40123456")
    doc_id = _cargar(cliente_api, t, p, req, desde="2026-03-01", hasta="2027-03-01", solo_declarado=True)["documento_id"]
    with tenant_session(t.tenant_id) as s:
        s.execute(
            text("UPDATE modulo1.documento SET estado_confirmacion = 'verificado' WHERE documento_id = CAST(:d AS uuid)"),
            {"d": doc_id},
        )
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": p}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    item = r.json()["documentos"][0]
    assert item["estado_presentacion"] == "verificada"
    assert item["estados_adicionales"] == ["sin_archivo_respaldo"]
    assert item["archivo_validacion"] == "sin_archivo"

