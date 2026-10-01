"""Alta de catálogos OC: duplicados normalizados."""
from __future__ import annotations

from app.comun.normalizar_texto import normalizar_clave
from app.db import tenant_session
from app.modules.oc.catalogos_maestros import resolver_operadora


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


def test_sugerencia_operadora_por_similitud_no_alfabetica(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    headers = t.headers("responsable_legajos")
    for nombre in ("Pluspetrol", "YPF"):
        r = cliente_api.post("/v1/comandos/alta_operadora_oc", json={"nombre": nombre}, headers=headers)
        assert r.status_code == 200, r.text
    with tenant_session(t.tenant_id) as session:
        _, err = resolver_operadora(session, t.tenant_id, "YPF SA")
    assert err is not None
    assert "YPF" in err
    assert "Pluspetrol" not in err
