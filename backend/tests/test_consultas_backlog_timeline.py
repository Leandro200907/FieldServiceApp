"""Consultas backlog OC, cobertura y timeline (D-A bis)."""
from __future__ import annotations

pytest_plugins = ("tests.test_orquestacion",)

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text

from tests.test_a04_alcance_evaluacion import _asignar, _escenario, _segundo_supervisor
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _contar_evaluaciones(s, extra: str = "") -> int:
    return s.execute(text(f"SELECT count(*) FROM modulo1.evaluacion_habilitacion {extra}")).scalar()


def test_backlog_oc_cubierta(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    _escenario(sesion, t)
    sesion.commit()
    antes = _contar_evaluaciones(sesion)
    r = cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["clave_origen"] == "OC-1")
    assert item["estado_cobertura"] == "cubierta"
    assert "ultima_decision" not in item
    assert _contar_evaluaciones(sesion) == antes


def test_backlog_oc_motivo_112(cliente_api, tenant_de_prueba, sesion):
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
    r = cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("responsable_legajos"))
    item = next(i for i in r.json()["items"] if i["clave_origen"] == "OC-VTV")
    assert item["estado_cobertura"] == "no_cubierta"
    veh = next(p for p in item["por_tipo"] if p["tipo_sujeto"] == "vehiculo")
    assert veh["candidatos_cumplen"] == 0
    assert veh["motivo"] == "requisito_faltante: VTV — ningún legajo de tipo vehículo lo posee"


def test_backlog_empresa_vencida_bloquea(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(sesion, t.tenant_id, "Apto", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 9, 1))
    insertar_documento(sesion, t.tenant_id, "persona_0042", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t.tenant_id, "OC-EMP", clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    r = cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("responsable_legajos"))
    item = next(i for i in r.json()["items"] if i["clave_origen"] == "OC-EMP")
    assert item["estado_cobertura"] == "empresa_bloquea"


def test_supervisor_fuera_de_alcance_en_backlog(cliente_api, tenant_de_prueba, sesion):
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
    r = cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("supervisor"))
    item = next(i for i in r.json()["items"] if i["clave_origen"] == "OC-ALC")
    veh = next(p for p in item["por_tipo"] if p["tipo_sujeto"] == "vehiculo")
    assert veh["estado"] == "fuera_de_alcance"
    assert "fuera de tu alcance" in (veh["motivo"] or "")


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
