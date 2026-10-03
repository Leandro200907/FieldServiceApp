"""Ronda 1-b punto 6: nombres legibles, /yo enriquecido y auditoría con usuario."""
from __future__ import annotations

from tests.test_comandos_legajos import _ok, _post


def test_yo_incluye_tenant_usuario_y_legajo_etiqueta(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "alta_de_sujeto",
            {
                "tipo_sujeto": "persona",
                "identificador_natural": "36666111",
                "nombre_apellido": "Técnico Etiqueta",
                "sujeto_id": t.sujeto_tecnico,
            },
        )
    )
    yo = cliente_api.get("/v1/auth/yo", headers=t.headers("tecnico"))
    assert yo.status_code == 200, yo.text
    body = yo.json()
    assert body["tenant_nombre"].startswith("Tenant de prueba")
    assert body["usuario_email"] == f"tecnico@{t.slug}.test"
    assert body["usuario_nombre"] == "tecnico"
    assert "Técnico Etiqueta" in (body["legajo_etiqueta"] or "")


def test_log_auditoria_expone_usuario_nombre(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "alta_de_sujeto",
            {"tipo_sujeto": "vehiculo", "identificador_natural": "AA123BB"},
        )
    )
    r = cliente_api.get(
        "/v1/consultas/log_auditoria",
        params={"tipo": "LegajoCreado", "limit": 5},
        headers=t.headers("configuracion"),
    )
    assert r.status_code == 200, r.text
    eventos = r.json()["items"]
    assert eventos and eventos[0].get("usuario_nombre")
