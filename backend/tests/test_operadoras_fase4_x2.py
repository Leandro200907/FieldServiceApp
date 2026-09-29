"""Fase 4 X-2: fila con Requisito ID inválido no aborta las válidas."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar
from tests.test_operadoras_documentales import _ENCABEZADOS, _xlsx


def test_importacion_parcial_con_requisito_id_invalido(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto parcial")
    p = _alta_persona(cliente_api, t, "persona_parcial")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op A", "persona", "persona_parcial", p, "Apto parcial", req,
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
        ["Op B", "persona", "persona_parcial", p, "Apto parcial", req,
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T11:00:00+00:00", "", "", ""],
        ["Op C", "persona", "persona_parcial", p, "Apto parcial", "no-es-uuid",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T12:00:00+00:00", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filas_aceptadas"] == 2 and body["filas_rechazadas"] == 1
    assert len(body["resultados"]) == 2
    assert body["resultados"][0]["documento_id"] == doc["documento_id"]
    assert body["errores"][0]["fila"] == 8
