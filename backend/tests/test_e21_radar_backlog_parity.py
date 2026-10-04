"""E-21: radar_documental_backlog y backlog_oc comparten evaluación por OC."""
from __future__ import annotations

pytest_plugins = ("tests.test_orquestacion",)

from datetime import timedelta

from app.comun.reloj import hoy_del_tenant


def test_radar_y_backlog_coinciden_estado_y_alertas(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    hasta = hoy + timedelta(days=60)
    params = {"desde": hoy.isoformat(), "hasta": hasta.isoformat(), "limit": 50, "offset": 0}
    radar = cliente_api.get(
        "/v1/consultas/radar_documental_backlog",
        params=params,
        headers=t.headers("responsable_legajos"),
    )
    backlog = cliente_api.get(
        "/v1/consultas/backlog_oc",
        params={"limit": 50, "offset": 0, "vigencia_desde": hoy.isoformat()},
        headers=t.headers("responsable_legajos"),
    )
    assert radar.status_code == 200, radar.text
    assert backlog.status_code == 200, backlog.text
    por_clave_radar = {i["clave_origen"]: i for i in radar.json()["items"]}
    for item in backlog.json()["items"]:
        clave = item["clave_origen"]
        r = por_clave_radar.get(clave)
        assert r is not None, f"Falta {clave} en radar"
        assert r["estado_documental"] == item["estado_documental"], clave
        assert len(r.get("alertas_ciertas") or []) == len(item.get("alertas_ciertas") or []), clave
        assert bool(r.get("tiene_alertas")) == bool(item.get("tiene_alertas")), clave
