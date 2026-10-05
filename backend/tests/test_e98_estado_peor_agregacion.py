"""E-98: estado_peor del agregado multi-OC refleja el peor estado del motor."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.comun.reloj import hoy_del_tenant
from app.modules.consultas.requisitos_exigidos_legajo import AgregadoRequisitoExigido
from tests.test_comandos_legajos import _ok, _post
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


def _oc_ref(n: int = 1) -> dict[str, str]:
    return {
        "clave_origen": f"OC-{n}",
        "oc_id": f"id-{n}",
        "vigencia_desde": "2026-10-01",
        "vigencia_hasta": "2026-11-01",
    }


def _req(estado: str, **extra) -> dict:
    base = {
        "estado": estado,
        "requisito_definicion_id": "req-1",
        "nombre": "Req",
        "evidencia_id": extra.pop("evidencia_id", "doc-1"),
    }
    base.update(extra)
    return base


def test_estado_peor_sin_evaluaciones_arranca_sin_evaluacion():
    ag = AgregadoRequisitoExigido("r1", "R", "documento", "documento")
    assert ag.estado_peor == "sin_evaluacion"


def test_estado_peor_toma_peor_entre_dos_oc():
    ag = AgregadoRequisitoExigido("r1", "R", "documento", "documento")
    ag.actualizar_desde_eval(_req("vigente_todo_el_periodo"), _oc_ref(1))
    ag.actualizar_desde_eval(_req("vence_durante_periodo"), _oc_ref(2))
    assert ag.estado_peor == "vence_durante_periodo"


def test_estado_peor_todas_vigentes():
    ag = AgregadoRequisitoExigido("r1", "R", "documento", "documento")
    ag.actualizar_desde_eval(_req("vigente_todo_el_periodo"), _oc_ref(1))
    ag.actualizar_desde_eval(_req("vigente_todo_el_periodo"), _oc_ref(2))
    assert ag.estado_peor == "vigente_todo_el_periodo"


def test_estado_peor_faltante_gana():
    ag = AgregadoRequisitoExigido("r1", "R", "documento", "documento")
    ag.actualizar_desde_eval(_req("vigente_todo_el_periodo"), _oc_ref(1))
    ag.actualizar_desde_eval(_req("faltante", evidencia_id=None), _oc_ref(2))
    assert ag.estado_peor == "faltante"


def test_legajo_requisito_en_regla_sin_acciones_gestion(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    persona = "persona-e98-regla"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    req = insertar_definicion(sesion, t.tenant_id, "Apto E98", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, persona, req, hoy, hoy + timedelta(days=365))
    insertar_oc(sesion, t.tenant_id, "OC-E98-OK", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()
    body = _legajo(cliente_api, t, persona).json()
    fila = next(i for i in body["documentos"] if i["requisito_definicion_id"] == req)
    assert fila.get("evaluacion_backlog_estado") == "vigente_todo_el_periodo"
    assert not fila.get("gestion_tecnico")
    assert not fila.get("gestion_responsable")
    assert not fila.get("faltante_exigido")


def test_legajo_induccion_faltante_ofrece_registro_responsable(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    persona = "persona-e98-lucia"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    req_doc = insertar_definicion(sesion, t.tenant_id, "Apto E98L", "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            __import__("sqlalchemy").text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción E98", "l": loc_id},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_doc: "bloqueante_duro", req_ind: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, persona, req_doc, hoy, hoy + timedelta(days=365))
    insertar_oc(sesion, t.tenant_id, "OC-E98-LU", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()
    body = _legajo(cliente_api, t, persona).json()
    ind = next(i for i in body["inducciones"] if i["requisito"] == "Inducción E98")
    assert ind.get("evaluacion_backlog_estado") == "faltante"
    assert ind.get("faltante_exigido")
    assert ind.get("gestion_responsable") == "registrar_induccion"
