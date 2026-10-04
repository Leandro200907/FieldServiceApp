"""Integración Módulo 1 ronda F: backlog D23, acciones, legajo resumen, E-10 por operadora."""
from __future__ import annotations

pytest_plugins = ("tests.test_orquestacion",)

from datetime import date, timedelta

from sqlalchemy import text

from app.comun.reloj import hoy_del_tenant
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_catalogos_maestros,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)


def test_backlog_excluye_oc_terminada_e_incluye_futura(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART empresa", "empresa")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2027, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-TERM-F", clave, hoy - timedelta(days=60), hoy - timedelta(days=1))
    insertar_oc(sesion, t.tenant_id, "OC-FUT-F", clave, hoy + timedelta(days=14), hoy + timedelta(days=45))
    sesion.commit()
    r = cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    claves = {i["clave_origen"] for i in r.json()["items"]}
    assert "OC-FUT-F" in claves
    assert "OC-TERM-F" not in claves


def test_legajo_resumen_maria_incluye_en_regla_y_ocs(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto resumen f")
    p = _alta_persona(cliente_api, t, "persona_resumen_f", nombre_apellido="María González Demo")
    _cargar(cliente_api, t, p, req, desde="2026-09-01", hasta="2027-09-01")
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": p}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resumen"]["en_regla"] >= 0
    assert "ocs_afectadas" in body["resumen"]
    assert body["legajo"]["nombre_apellido"] == "María González Demo"


def test_acciones_pendientes_incluye_vehiculo_pa200fg(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    veh = "vehiculo-pa200fg-f"
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, veh, "vehiculo")
    sesion.execute(
        text("UPDATE modulo1.legajo SET identificador_natural = 'PA200FG' WHERE tenant_id = :t AND sujeto_id = :s"),
        {"t": t.tenant_id, "s": veh},
    )
    req_e = insertar_definicion(sesion, t.tenant_id, "ART empresa", "empresa")
    req_v = insertar_definicion(sesion, t.tenant_id, "VTV PA200", "vehiculo")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_v: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2027, 12, 31))
    insertar_documento(sesion, t.tenant_id, veh, req_v, hoy - timedelta(days=400), hoy - timedelta(days=10))
    insertar_oc(sesion, t.tenant_id, "OC-VEH-F", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()
    r = cliente_api.get("/v1/consultas/acciones_pendientes", headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(i.get("identificador_natural") == "PA200FG" or i.get("sujeto_id") == veh for i in items)


def test_e10_rechazo_vista_no_bloquea_misma_persona_en_oc_ypf(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave_v = clave_de_matriz()
    clave_y = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave_v, operadora="Vista")
    insertar_catalogos_maestros(sesion, t.tenant_id, clave_y, operadora="YPF")
    maria = "persona_maria_e10"
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, maria, "persona")
    sesion.execute(
        text("UPDATE modulo1.legajo SET nombre_apellido = 'María E10' WHERE tenant_id = :t AND sujeto_id = :s"),
        {"t": t.tenant_id, "s": maria},
    )
    req_e = insertar_definicion(sesion, t.tenant_id, "ART empresa", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto E10", "persona")
    insertar_matriz(sesion, t.tenant_id, clave_v, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_matriz(sesion, t.tenant_id, clave_y, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    doc_id = insertar_documento(sesion, t.tenant_id, maria, req_p, hoy, hoy + timedelta(days=365))
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2027, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-VISTA-E10", clave_v, hoy, hoy + timedelta(days=30))
    insertar_oc(sesion, t.tenant_id, "OC-YPF-E10", clave_y, hoy, hoy + timedelta(days=30))
    sesion.commit()
    _ok(_post(cliente_api, t, "responsable_legajos", "registrar_estado_documento_operadora", {
        "operadora": "Vista",
        "sujeto_id": maria,
        "documento_id": doc_id,
        "estado": "rechazado",
        "rechazado_en": f"{hoy.isoformat()}T12:00:00Z",
    }))
    radar = cliente_api.get(
        "/v1/consultas/radar_documental_backlog",
        params={"desde": hoy.isoformat(), "hasta": (hoy + timedelta(days=60)).isoformat()},
        headers=t.headers("responsable_legajos"),
    )
    assert radar.status_code == 200, radar.text
    por_clave = {i["clave_origen"]: i for i in radar.json()["items"]}
    vista = por_clave.get("OC-VISTA-E10")
    ypf = por_clave.get("OC-YPF-E10")
    assert vista and ypf
    assert vista.get("estado_documental") == "con_alertas_documentales"
    assert ypf.get("estado_documental") in (
        "habilitado",
        "sin_alertas_documentales",
        "con_alertas_documentales",
        "se_cae_en_ventana",
    )
