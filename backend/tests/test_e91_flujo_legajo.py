"""E-91: ficha alineada al backlog — inducción (responsable) y documento (técnico)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.comun.reloj import hoy_del_tenant
from tests.test_comandos_legajos import _alta_def, _alta_persona, _ok, _post
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


def _legajo(cliente_api, t, sujeto_id):
    return cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": sujeto_id}, headers=t.headers("responsable_legajos"))


def test_e91_induccion_faltante_y_registro_responsable(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    persona = "persona-e91-lucia"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    req_doc = insertar_definicion(sesion, t.tenant_id, "Apto E91", "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            __import__("sqlalchemy").text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción E91", "l": loc_id},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_doc: "bloqueante_duro", req_ind: "bloqueante_duro"})
    doc_apto = insertar_documento(sesion, t.tenant_id, persona, req_doc, hoy, hoy + timedelta(days=365))
    insertar_oc(sesion, t.tenant_id, "OC-E91-LU", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    r = _legajo(cliente_api, t, persona)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resumen"]["exigidos"] == 2
    assert body["resumen"]["en_regla_exigidos"] == 1
    assert body["resumen"]["sin_documento"] == 1
    nombres = {i["requisito"] for i in body["inducciones"] + body["documentos"]}
    assert "Inducción E91" in nombres

    reg = _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_induccion",
            {
                "persona_id": persona,
                "locacion_id": loc_id,
                "requisito_definicion_id": req_ind,
                "vigente_desde": hoy.isoformat(),
                "vigente_hasta": (hoy + timedelta(days=365)).isoformat(),
                "evidencia": doc_apto,
            },
        )
    )
    assert reg["induccion_id"]

    r2 = _legajo(cliente_api, t, persona)
    assert r2.json()["resumen"]["en_regla_exigidos"] == 2
    assert r2.json()["resumen"]["exigidos"] == 2


def test_e91_documento_faltante_tecnico_incorpora(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    req_a = insertar_definicion(sesion, t.tenant_id, "ART E91", "persona")
    req_b = insertar_definicion(sesion, t.tenant_id, "Licencia E91", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req_a: "bloqueante_duro", req_b: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-E91-DOC", clave, hoy, hoy + timedelta(days=30))
    persona = _alta_persona(cliente_api, t, "DNI-E91-DOC", t.sujeto_tecnico, nombre_apellido="Técnico E91")
    insertar_documento(sesion, t.tenant_id, persona, req_a, hoy, hoy + timedelta(days=200))
    sesion.commit()

    r = _legajo(cliente_api, t, persona)
    assert r.status_code == 200
    assert r.json()["resumen"]["exigidos"] == 2
    assert r.json()["resumen"]["en_regla_exigidos"] == 1

    prop = _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req_b,
                "vigente_desde": hoy.isoformat(),
                "vigente_hasta": (hoy + timedelta(days=400)).isoformat(),
            },
        )
    )
    assert prop["estado_version"] == "propuesta"

    mi = cliente_api.get("/v1/consultas/mi_legajo", headers=t.headers("tecnico"))
    assert mi.status_code == 200
    docs = mi.json()["persona"]["documentos"]
    falt = next((d for d in docs if d.get("requisito_definicion_id") == req_b), None)
    assert falt is not None
    assert falt.get("gestion_tecnico") == "incorporar" or falt.get("faltante_exigido")
