"""Fase 4 X-5: validación Pydantic, Documento ID y media type XLSX."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar
from tests.test_operadoras_documentales import _ENCABEZADOS, _alta_operadora, _xlsx


def test_operadora_vacia_rechaza_solo_esa_fila(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op OK")
    req = _alta_def(cliente_api, t, "Apto vacio")
    p = _alta_persona(cliente_api, t, "persona_vacia_x5")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op OK", "persona", "persona_vacia_x5", p, "Apto vacio", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
        ["   ", "persona", "persona_vacia_x5", p, "Apto vacio", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T11:00:00+00:00", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filas_aceptadas"] == 1
    assert body["errores"][0]["codigo"] == "fila_invalida"
    assert body["resultados"][0]["documento_id"] == doc["documento_id"]


def test_columna_documento_id_resuelve_documento(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Doc")
    req = _alta_def(cliente_api, t, "Apto docid")
    p = _alta_persona(cliente_api, t, "persona_docid_x5")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op Doc", "persona", "persona_docid_x5", p, "Apto docid", "", doc["documento_id"],
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["filas_aceptadas"] == 1
    assert r.json()["resultados"][0]["documento_id"] == doc["documento_id"]


def test_importacion_exige_media_type_xlsx(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    headers = {**t.headers("responsable_legajos"), "Content-Type": "application/octet-stream"}
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx([_ENCABEZADOS, ["Op", "persona", "x", "", "Apto", "", "", "", "exportado", "2026-01-01", "", "", ""]]),
        headers=headers,
    )
    assert r.status_code == 415, r.text


def test_operadora_inexistente_rechaza_fila(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "YPF")
    req = _alta_def(cliente_api, t, "Apto cat")
    p = _alta_persona(cliente_api, t, "persona_cat_op")
    _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Inventada SA", "persona", "persona_cat_op", p, "Apto cat", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    err = r.json()["errores"][0]
    assert err["codigo"] == "operadora_inexistente"
    assert "no está en el catálogo" in err["mensaje"]
