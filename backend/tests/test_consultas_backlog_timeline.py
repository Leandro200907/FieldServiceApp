"""Timeline de recursos (consulta Módulo 1)."""
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


def test_timeline_sin_rango_usa_ventana_por_defecto(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    from app.comun.reloj import hoy_del_tenant

    hoy = hoy_del_tenant(sesion, t.tenant_id)
    r = cliente_api.get("/v1/consultas/timeline_recursos", headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hoy"] == hoy.isoformat()
    assert body["desde"]
    assert body["hasta"]
    assert (date.fromisoformat(body["hasta"]) - date.fromisoformat(body["desde"])).days <= 366


def test_timeline_quiebre_dentro_de_oc(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 1, 1), date(2026, 10, 12))
    insertar_oc(sesion, t.tenant_id, "OC-TIME", clave, date(2026, 10, 5), date(2026, 10, 25))
    sesion.commit()
    r = cliente_api.get(
        "/v1/consultas/timeline_recursos?desde=2026-10-01&hasta=2026-11-30",
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    recurso = next(i for i in r.json()["items"] if i["sujeto_id"] == "persona_0042")
    cruce = next(c for c in recurso["ocs"] if c["clave_origen"] == "OC-TIME")
    assert cruce["llega_cubierto"] is False
    assert any(q["requisito"] == "Apto médico" for q in cruce["quiebres"])
    assert any(q["fecha"] == "2026-10-12" and q.get("tipo") == "vence" for q in cruce["quiebres"])


def test_timeline_ultimo_dia_inclusive_no_quiebre(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 1, 1), date(2026, 10, 25))
    insertar_oc(sesion, t.tenant_id, "OC-FIN", clave, date(2026, 10, 5), date(2026, 10, 25))
    sesion.commit()
    r = cliente_api.get(
        "/v1/consultas/timeline_recursos?desde=2026-10-01&hasta=2026-11-30",
        headers=t.headers("responsable_legajos"),
    )
    recurso = next(i for i in r.json()["items"] if i["sujeto_id"] == "persona_0042")
    cruce = next(c for c in recurso["ocs"] if c["clave_origen"] == "OC-FIN")
    assert cruce["quiebres"] == []
    assert cruce["llega_cubierto"] is True


def test_timeline_no_dice_vence_si_documento_empieza_despues(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 11, 10), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-INI", clave, date(2026, 10, 5), date(2026, 10, 25))
    sesion.commit()
    r = cliente_api.get(
        "/v1/consultas/timeline_recursos?desde=2026-10-01&hasta=2026-11-30",
        headers=t.headers("responsable_legajos"),
    )
    recurso = next(i for i in r.json()["items"] if i["sujeto_id"] == "persona_0042")
    cruce = next(c for c in recurso["ocs"] if c["clave_origen"] == "OC-INI")
    assert all(q.get("tipo") != "vence" for q in cruce["quiebres"])
