"""Ronda 1-b punto 7: radar con disponibilidad por tipo e impacto."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from tests.test_consultas import CLIENTE, LOCACION, TIPO, _legajo, _matriz, _oc, _requisito


def test_radar_backlog_incluye_disponibilidad_por_tipo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    clave = f"OC-R1B-{uuid.uuid4().hex[:6]}"
    with tenant_session(t.tenant_id) as s:
        rid = _requisito(s, t, "Req radar r1b", "persona")
        _matriz(s, t, 1, "2026-10-01", "2026-12-31", [rid])
        _oc(s, t, clave, "2026-10-15", "2026-11-15")
        oc_id = s.execute(
            text("SELECT oc_id FROM modulo1.oc WHERE clave_origen = :c"),
            {"c": clave},
        ).scalar()
    r = cliente_api.get(
        "/v1/consultas/radar_documental_backlog",
        params={"desde": "2026-10-01", "hasta": "2026-11-30", "q": clave, "limit": 10},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items
    item = items[0]
    assert item.get("operadora_nombre") is not None or item.get("cliente_id")
    assert "disponibilidad_por_tipo" in item
    assert isinstance(item["disponibilidad_por_tipo"], list)
    det = cliente_api.get(
        "/v1/consultas/radar_documental_oc",
        params={"oc_id": str(oc_id)},
        headers=t.headers("responsable_legajos"),
    )
    assert det.status_code == 200, det.text
    assert "disponibilidad_por_tipo" in det.json()
