"""Ronda 1-b punto 1: nombre y apellido en legajo de persona (D14)."""
from __future__ import annotations

from tests.test_comandos_legajos import _ok, _post


def test_alta_persona_guarda_nombre_y_consulta_muestra_dni_secundario(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    body = {
        "tipo_sujeto": "persona",
        "identificador_natural": "30111222",
        "nombre_apellido": "Ana Test Ronda1B",
    }
    sid = _ok(_post(cliente_api, t, "responsable_legajos", "alta_de_sujeto", body))["sujeto_id"]
    legajo = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": sid}, headers=t.headers("responsable_legajos"))
    assert legajo.status_code == 200, legajo.text
    datos = legajo.json()["legajo"]
    assert datos["nombre_apellido"] == "Ana Test Ronda1B"
    assert datos["identificador_natural"] == "30111222"
    busqueda = cliente_api.get(
        "/v1/consultas/sujetos",
        params={"q": "Ana Test", "limit": 20},
        headers=t.headers("responsable_legajos"),
    )
    assert busqueda.status_code == 200
    ids = [i["sujeto_id"] for i in busqueda.json()["items"]]
    assert sid in ids


def test_corregir_nombre_legajo_persona(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    sid = _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "alta_de_sujeto",
            {"tipo_sujeto": "persona", "identificador_natural": "30999888", "nombre_apellido": "Nombre Viejo"},
        )
    )["sujeto_id"]
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "corregir_nombre_legajo_persona",
            {"sujeto_id": sid, "nombre_apellido": "Nombre Nuevo"},
        )
    )
    legajo = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": sid}, headers=t.headers("responsable_legajos")).json()
    assert legajo["legajo"]["nombre_apellido"] == "Nombre Nuevo"
