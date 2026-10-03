"""Ronda 1-b punto 3: resumen compuesto con por_vencer y estados de presentación."""
from __future__ import annotations

from datetime import timedelta

from app.comun.reloj import hoy_del_tenant
from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _cargar, _ok, _post


def test_mi_legajo_resumen_incluye_por_vencer(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)
    req = _alta_def(cliente_api, t, "Por vencer r1b")
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "alta_de_sujeto",
            {
                "tipo_sujeto": "persona",
                "identificador_natural": "28888111",
                "nombre_apellido": "Técnico Mi Legajo",
                "sujeto_id": t.sujeto_tecnico,
            },
        )
    )
    hasta = (hoy + timedelta(days=10)).isoformat()
    desde = (hoy - timedelta(days=30)).isoformat()
    _cargar(cliente_api, t, t.sujeto_tecnico, req, desde=desde, hasta=hasta)
    r = cliente_api.get("/v1/consultas/mi_legajo", headers=t.headers("tecnico"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "por_vencer" in body["resumen"]
    assert body["persona"]["documentos"][0]["estado_presentacion"] in (
        "por_vencer",
        "verificada",
        "declarada",
        "archivo_en_revision",
    )
