"""Alta de catálogos OC: duplicados normalizados."""
from __future__ import annotations

from app.comun.normalizar_texto import normalizar_clave


def test_normalizar_clave_ignora_puntos_acentos_y_mayusculas():
    assert normalizar_clave("Y.P.F.") == normalizar_clave("YPF") == "ypf"
    assert normalizar_clave(" ypf ") == "ypf"


def test_alta_operadora_oc_duplicada_como_locacion_y_tipo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    headers = t.headers("responsable_legajos")
    r1 = cliente_api.post("/v1/comandos/alta_operadora_oc", json={"nombre": "YPF"}, headers=headers)
    assert r1.status_code == 200, r1.text
    for nombre in ("ypf", " YPF ", "Y.P.F."):
        r = cliente_api.post("/v1/comandos/alta_operadora_oc", json={"nombre": nombre}, headers=headers)
        assert r.status_code == 422, (nombre, r.text)
        assert "duplicad" in r.json()["error"]["mensaje"].lower()
