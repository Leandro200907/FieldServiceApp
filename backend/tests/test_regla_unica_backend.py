"""Regla 15: una sola implementación en backend y campos precalculados en consultas."""
from __future__ import annotations

from datetime import date, timedelta

from app.comun.reloj import hoy_del_tenant
from tests.test_comandos_legajos import _post
from tests.test_e91_flujo_legajo import _legajo
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_catalogos_maestros,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)

pytest_plugins = ("tests.test_orquestacion",)


def test_legajo_campos_tarjeta_codigo_y_resumen_exigidos(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_r15", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_r15", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART R15", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Licencia R15", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_r15", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_r15", req_p, hoy, hoy + timedelta(days=120))
    insertar_oc(sesion, t.tenant_id, "OC-R15", clave, hoy, hoy + timedelta(days=60))
    sesion.commit()

    body = _legajo(cliente_api, t, "persona_r15").json()
    assert body["hoy"] == hoy.isoformat()
    resumen = body["resumen"]
    assert "pendientes_revision" in resumen
    assert "proximo_vencimiento" in resumen
    assert resumen["proximo_vencimiento"] == (hoy + timedelta(days=120)).isoformat()

    fila = next(d for d in body["documentos"] if d["requisito_definicion_id"] == req_p)
    assert fila["codigo_estado"] == fila["estado_presentacion"]
    assert fila["tarjeta_exigido"] in ("vigentes", "por_vencer", "vencidos", "sin_documento")


def test_matrices_y_backlog_incluyen_hoy(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_m", "empresa")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART M", "empresa")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-M", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    rm = cliente_api.get("/v1/consultas/matrices", headers=t.headers("responsable_legajos"))
    assert rm.status_code == 200
    assert rm.json()["hoy"] == hoy.isoformat()
    assert rm.json()["items"][0]["vigente_hoy"] is True

    rb = cliente_api.get("/v1/consultas/backlog_oc", params={"estado": "activo"}, headers=t.headers("responsable_legajos"))
    assert rb.status_code == 200
    assert rb.json()["hoy"] == hoy.isoformat()


def test_acciones_pendientes_hoy_y_accion_vencida(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_lenta", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_lenta", req_p, hoy - timedelta(days=60), hoy - timedelta(days=1))
    insertar_oc(sesion, t.tenant_id, "OC-VENC", clave, hoy - timedelta(days=10), hoy + timedelta(days=20))
    sesion.commit()

    r = cliente_api.get(
        "/v1/consultas/acciones_pendientes",
        params={"mes": hoy.strftime("%Y-%m"), "limit": 50},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["hoy"] == hoy.isoformat()
    assert data["items"]
    for i in data["items"]:
        assert i["accion_vencida"] == (i["fecha_limite"] < data["hoy"])


def test_calendario_estado_visual_calendario(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    insertar_legajo(sesion, t.tenant_id, "persona_cal", "persona")
    req = insertar_definicion(sesion, t.tenant_id, "VTV cal", "persona")
    insertar_documento(sesion, t.tenant_id, "persona_cal", req, hoy, hoy + timedelta(days=20))
    sesion.commit()

    r = cliente_api.get(
        "/v1/consultas/calendario_vigencias",
        params={"desde": hoy.isoformat(), "hasta": (hoy + timedelta(days=40)).isoformat()},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["sujeto_id"] == "persona_cal")
    assert item["estado_visual_calendario"] == "verificada"


def test_ficha_y_timeline_por_vencer_mismo_plazo_tenant(cliente_api, tenant_de_prueba, sesion):
    """Con plazo_aviso=10, vence en 15 días no es «por vencer» (antes timeline usaba 30 fijo)."""
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    r_cfg = _post(
        cliente_api,
        t,
        "configuracion",
        "configurar_alertas",
        {"plazo_aviso_dias": 10, "escalamiento_dias": 7, "rol_escalamiento": "supervisor"},
    )
    assert r_cfg.status_code == 200, r_cfg.text

    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_plazo", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_plazo_15", "persona")
    insertar_legajo(sesion, t.tenant_id, "persona_plazo_7", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART plazo", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto plazo", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_plazo", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_plazo_15", req_p, hoy, hoy + timedelta(days=15))
    insertar_documento(sesion, t.tenant_id, "persona_plazo_7", req_p, hoy, hoy + timedelta(days=7))
    insertar_oc(sesion, t.tenant_id, "OC-PLAZO", clave, hoy, hoy + timedelta(days=60))
    sesion.commit()

    def _estados(sujeto: str) -> tuple[str, str, str]:
        body = _legajo(cliente_api, t, sujeto).json()
        fila = next(d for d in body["documentos"] if d["requisito_definicion_id"] == req_p)
        r_tl = cliente_api.get(
            "/v1/consultas/timeline_recursos",
            params={"desde": hoy.isoformat(), "hasta": (hoy + timedelta(days=60)).isoformat()},
            headers=t.headers("responsable_legajos"),
        )
        tramo = next(
            tr for tr in next(i for i in r_tl.json()["items"] if i["sujeto_id"] == sujeto)["tramos"]
            if tr["requisito_definicion_id"] == req_p
        )
        return fila["estado_presentacion"], fila["tarjeta_exigido"], tramo["estado_visual"]

    pres_15, tarj_15, vis_15 = _estados("persona_plazo_15")
    assert pres_15 == "verificada" and tarj_15 == "vigentes" and vis_15 == "vigente"

    pres_7, tarj_7, vis_7 = _estados("persona_plazo_7")
    assert pres_7 == "por_vencer" and tarj_7 == "por_vencer" and vis_7 == "por_vencer"
