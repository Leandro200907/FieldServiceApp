"""Ronda 1-b punto 5: timeline filtra por nombre y apellido."""
from __future__ import annotations

from tests.test_comandos_legajos import _ok, _post


def test_timeline_busca_por_nombre_apellido(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    sid = _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "alta_de_sujeto",
            {
                "tipo_sujeto": "persona",
                "identificador_natural": "35555111",
                "nombre_apellido": "Timeline Busqueda Unica",
            },
        )
    )["sujeto_id"]
    r = cliente_api.get(
        "/v1/consultas/timeline_recursos",
        params={"desde": "2026-10-01", "hasta": "2026-11-30", "q": "Timeline Busqueda"},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    ids = [i["sujeto_id"] for i in r.json()["items"]]
    assert sid in ids
    item = next(i for i in r.json()["items"] if i["sujeto_id"] == sid)
    assert item.get("nombre_apellido") == "Timeline Busqueda Unica"
