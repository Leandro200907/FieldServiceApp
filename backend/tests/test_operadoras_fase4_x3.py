"""Fase 4 X-3: fecha inválida en una fila no rechaza la planilla entera."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar
from tests.test_operadoras_documentales import _ENCABEZADOS, _alta_operadora, _xlsx


def test_fecha_invalida_en_una_fila_importa_las_demas(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op OK")
    _alta_operadora(cliente_api, t, "Op Mal")
    req = _alta_def(cliente_api, t, "Apto fecha")
    p = _alta_persona(cliente_api, t, "persona_fecha_x3")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op OK", "persona", "persona_fecha_x3", p, "Apto fecha", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
        ["Op Mal", "persona", "persona_fecha_x3", p, "Apto fecha", req, "",
         "no-es-fecha", "2027-09-25", "exportado", "2026-09-27T11:00:00+00:00", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filas_aceptadas"] == 1 and body["filas_rechazadas"] == 1
    assert body["resultados"][0]["documento_id"] == doc["documento_id"]
    assert body["errores"][0]["fila"] == 7
    assert body["errores"][0]["codigo"] == "fecha_invalida"


def test_fecha_texto_dd_mm_aaaa(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Fecha AR")
    req = _alta_def(cliente_api, t, "Apto ddmm")
    p = _alta_persona(cliente_api, t, "persona_ddmm")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op Fecha AR", "persona", "persona_ddmm", p, "Apto ddmm", req, "",
         "27/09/2026", "25/09/2027", "exportado", "27/09/2026", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["filas_aceptadas"] == 1
    assert r.json()["resultados"][0]["documento_id"] == doc["documento_id"]
