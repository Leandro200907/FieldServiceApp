"""Acciones pendientes (modo consulta Módulo 1)."""
from __future__ import annotations

pytest_plugins = ("tests.test_orquestacion",)

from datetime import date

from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)


def test_acciones_pendientes_orden_y_efecto(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave_a = clave_de_matriz()
    clave_b = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_lenta", "persona")
    insertar_legajo(sesion, t.tenant_id, "persona_rapida", "persona")
    insertar_legajo(sesion, t.tenant_id, "vehiculo_x", "vehiculo")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    req_v = insertar_definicion(sesion, t.tenant_id, "VTV", "vehiculo")
    insertar_matriz(sesion, t.tenant_id, clave_a, {req_e: "bloqueante_duro", req_p: "bloqueante_duro", req_v: "bloqueante_duro"})
    insertar_matriz(sesion, t.tenant_id, clave_b, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_lenta", req_p, date(2026, 1, 1), date(2026, 10, 20))
    insertar_documento(sesion, t.tenant_id, "persona_rapida", req_p, date(2026, 1, 1), date(2026, 10, 8))
    insertar_oc(sesion, t.tenant_id, "OC-ALERT", clave_a, date(2026, 10, 1), date(2026, 10, 25))
    insertar_oc(sesion, t.tenant_id, "OC-REN", clave_b, date(2026, 10, 1), date(2026, 10, 25))
    sesion.commit()

    r = cliente_api.get(
        "/v1/consultas/acciones_pendientes",
        params={"mes": "2026-10", "limit": 50},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 2
    assert all(i.get("efecto") for i in items)
    assert any(i["genera_alerta_cierta"] for i in items)

    def rank(a: dict) -> tuple:
        return (
            0 if a.get("genera_alerta_cierta") else 1,
            a.get("fecha_limite") or "",
            -len(a.get("ocs_afectadas") or []),
        )

    ranks = [rank(i) for i in items]
    assert ranks == sorted(ranks)
    assert items[0]["genera_alerta_cierta"] is True
    lenta = [i for i in items if i["legajo_id"] == "persona_lenta"]
    assert lenta
    assert any(len(i["ocs_afectadas"]) >= 2 for i in lenta)
