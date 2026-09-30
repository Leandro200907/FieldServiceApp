"""Backlog M1 sin veredicto de cobertura (D-E)."""
from __future__ import annotations

pytest_plugins = ("tests.test_orquestacion",)

from datetime import date

from sqlalchemy import text

from app.db import tenant_session
from tests.test_a04_alcance_evaluacion import _asignar
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_catalogos_maestros,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)


def test_backlog_sin_alertas(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-OK", clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    r = cliente_api.get("/v1/consultas/backlog_oc", params={"q": "OC-OK"}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["tiene_alertas"] is False
    assert "estado_cobertura" not in item
    assert item["operadora_nombre"]


def test_backlog_no_persiste_evaluacion(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-NOPERS", clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    with tenant_session(t.tenant_id) as s:
        antes = s.execute(text("SELECT count(*) FROM modulo1.evaluacion_habilitacion")).scalar()
    assert cliente_api.get("/v1/consultas/backlog_oc", params={"q": "OC-NOPERS"}, headers=t.headers("responsable_legajos")).status_code == 200
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.evaluacion_habilitacion")).scalar() == antes


def test_alerta_tipo_sin_habilitados(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "vehiculo_x", "vehiculo")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_v = insertar_definicion(sesion, t.tenant_id, "VTV", "vehiculo")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_v: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-VTV", clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    item = cliente_api.get("/v1/consultas/backlog_oc", params={"q": "OC-VTV"}, headers=t.headers("responsable_legajos")).json()["items"][0]
    codigos = {a["codigo"] for a in item["alertas_ciertas"]}
    assert "tipo_sin_habilitados" in codigos


def test_impacto_inclusive_siete_dias(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 1, 1), date(2026, 11, 18))
    insertar_oc(sesion, t.tenant_id, "OC-IMP", clave, date(2026, 11, 10), date(2026, 11, 25))
    sesion.commit()
    det = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-IMP"}, headers=t.headers("responsable_legajos")).json()
    persona_imp = next(i for i in det["impacto_por_tipo"] if i["tipo_sujeto"] == "persona")
    assert persona_imp["dias_sin_habilitados"] == 7


def test_supervisor_fuera_de_alcance(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_A", "persona")
    insertar_legajo(sesion, t.tenant_id, "vehiculo_Z", "vehiculo")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto", "persona")
    req_v = insertar_definicion(sesion, t.tenant_id, "VTV", "vehiculo")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro", req_v: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_A", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-ALC", clave, date(2026, 10, 1), date(2026, 10, 5))
    _asignar(sesion, t.tenant_id, "persona_A", t.usuarios["supervisor"])
    sesion.commit()
    item = cliente_api.get("/v1/consultas/backlog_oc", params={"q": "OC-ALC"}, headers=t.headers("supervisor")).json()["items"][0]
    assert "vehiculo" in item["tipos_fuera_de_alcance"]
    veh = next(d for d in item["disponibilidad_por_tipo"] if d["tipo_sujeto"] == "vehiculo")
    assert all("nat-vehiculo_Z" not in x.get("nombre", "") for grupo in (
        veh["habilitados_toda_ventana"], veh["se_cae_en_ventana"], veh["no_habilitados"],
    ) for x in grupo)


def test_supervisor_sin_alerta_si_unico_habilitado_fuera_de_universo(cliente_api, tenant_de_prueba, sesion):
    """El único habilitado está fuera del universo: no hay alerta cierta de tipo (no es cierto)."""
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_fuera", "persona")
    insertar_legajo(sesion, t.tenant_id, "persona_propia", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_fuera", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-FUERA", clave, date(2026, 10, 1), date(2026, 10, 5))
    _asignar(sesion, t.tenant_id, "persona_propia", t.usuarios["supervisor"])
    sesion.commit()
    item = cliente_api.get("/v1/consultas/backlog_oc", params={"q": "OC-FUERA"}, headers=t.headers("supervisor")).json()["items"][0]
    assert not any(a["codigo"] == "tipo_sin_habilitados" and a.get("tipo_sujeto") == "persona" for a in item["alertas_ciertas"])
    persona = next(d for d in item["disponibilidad_por_tipo"] if d["tipo_sujeto"] == "persona")
    nombres = {x["nombre"] for x in persona["habilitados_toda_ventana"]}
    assert "nat-persona_fuera" not in nombres
    assert "hay recursos habilitados fuera de tu alcance" in persona["texto"].lower()


def test_planilla_por_nombres_y_error_fila(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_catalogos_maestros(
        sesion, t.tenant_id, clave,
        operadora="YPF", locacion="Loma La Lata", tipo_servicio="Wireline",
    )
    sesion.commit()
    lote = "00000000-0000-4000-8000-000000000101"
    filas = [
        {
            "clave_origen": "OC-NOM-1",
            "referencia": "r1",
            "operadora": "YPF",
            "locacion": "Loma La Lata",
            "tipo_servicio": "Wireline",
            "vigencia_desde": "2026-10-01",
            "vigencia_hasta": "2026-10-10",
        },
        {
            "clave_origen": "OC-NOM-2",
            "operadora": "Desconocida SA",
            "locacion": "X",
            "tipo_servicio": "Wireline",
            "vigencia_desde": "2026-10-01",
            "vigencia_hasta": "2026-10-10",
        },
    ]
    r = cliente_api.post(
        "/v1/comandos/importar_lote_oc",
        json={"lote_id": lote, "origen": "planilla", "filas": filas},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["filas_aceptadas"] == 1
    assert body["filas_rechazadas"] == 1
    assert "operadora desconocida" in body["detalle_filas_rechazadas"][0]["motivo"].lower()


def test_reprogramar_oc_historial(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-REP", clave, date(2026, 10, 1), date(2026, 10, 5))
    oc_id = sesion.execute(text("SELECT oc_id::text FROM modulo1.oc WHERE clave_origen = 'OC-REP'")).scalar()
    sesion.commit()
    r = cliente_api.post(
        "/v1/comandos/reprogramar_oc",
        json={
            "oc_id": oc_id,
            "vigencia_desde": "2026-11-01",
            "vigencia_hasta": "2026-11-15",
            "motivo": "a solicitud del cliente",
        },
        headers={**t.headers("responsable_legajos"), "Idempotency-Key": "rep-oc-1"},
    )
    assert r.status_code == 200, r.text
    det = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-REP"}, headers=t.headers("responsable_legajos")).json()
    assert det["reprogramada"] is True
    assert len(det["historial_compromiso"]) >= 1


def test_backlog_alerta_empresa_no_habilitada(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-EMP-NH", clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    item = cliente_api.get("/v1/consultas/backlog_oc", params={"q": "OC-EMP-NH"}, headers=t.headers("responsable_legajos")).json()["items"][0]
    assert any(a["codigo"] == "empresa_no_habilitada" for a in item["alertas_ciertas"])


def test_backlog_alerta_sin_matriz(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_oc(sesion, t.tenant_id, "OC-SIN-MAT", clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    item = cliente_api.get("/v1/consultas/backlog_oc", params={"q": "OC-SIN-MAT"}, headers=t.headers("responsable_legajos")).json()["items"][0]
    assert any(a["codigo"] == "sin_matriz" for a in item["alertas_ciertas"])


def test_reprogramar_comparacion_antes_despues(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto médico", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 1, 1), date(2026, 11, 18))
    insertar_oc(sesion, t.tenant_id, "OC-CMP", clave, date(2026, 11, 10), date(2026, 11, 12))
    oc_id = sesion.execute(text("SELECT oc_id::text FROM modulo1.oc WHERE clave_origen = 'OC-CMP'")).scalar()
    sesion.commit()
    r = cliente_api.post(
        "/v1/comandos/reprogramar_oc",
        json={
            "oc_id": oc_id,
            "vigencia_desde": "2026-11-10",
            "vigencia_hasta": "2026-11-25",
            "motivo": "extensión de ventana",
        },
        headers={**t.headers("responsable_legajos"), "Idempotency-Key": "rep-oc-cmp"},
    )
    assert r.status_code == 200, r.text
    cmp = r.json()["comparacion_documental"]
    assert cmp["documental_anterior"]["tiene_alertas"] is False
    assert cmp["documental_nuevo"]["tiene_alertas"] is True
    assert any("vencimiento" in m for m in cmp["mensajes"])


def test_filtro_mes_y_operadora(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave, operadora="Operadora A")
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-OCT", clave, date(2026, 10, 5), date(2026, 10, 20))
    sesion.commit()
    r = cliente_api.get(
        "/v1/consultas/backlog_oc",
        params={"mes": "2026-10", "operadora_id": clave["c"]},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200
    assert any(i["clave_origen"] == "OC-OCT" for i in r.json()["items"])
