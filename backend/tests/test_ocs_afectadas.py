"""OCs afectadas cuando el documento no cubre el período de la OC."""
from __future__ import annotations

from datetime import date

import pytest

from app.modules.consultas.ocs_afectadas import (
    oc_en_curso,
    ordenar_ocs_afectadas,
    referencia_oc,
    requisito_sin_cobertura_en_periodo,
)
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)

pytest_plugins = ("tests.test_orquestacion",)


def test_requisito_sin_cobertura_incluye_alertas_temporales():
    assert requisito_sin_cobertura_en_periodo({"estado": "vence_durante_periodo"})
    assert requisito_sin_cobertura_en_periodo({"estado": "vencido_antes_inicio"})
    assert requisito_sin_cobertura_en_periodo({"estado": "faltante"})
    assert requisito_sin_cobertura_en_periodo({"estado": "pendiente_revision"})
    assert requisito_sin_cobertura_en_periodo({"estado": "evidencia_invalida"})
    assert not requisito_sin_cobertura_en_periodo({"estado": "vigente_todo_el_periodo"})


def test_ordenar_ocs_en_curso_primero():
    hoy = date(2026, 10, 3)
    ocs = [
        referencia_oc({"clave_origen": "OC-B", "oc_id": "2", "vigencia_desde": date(2026, 10, 16), "vigencia_hasta": date(2026, 10, 22)}),
        referencia_oc({"clave_origen": "OC-A", "oc_id": "1", "vigencia_desde": date(2026, 9, 28), "vigencia_hasta": date(2026, 11, 2)}),
    ]
    ordenadas = ordenar_ocs_afectadas(ocs, hoy)
    assert [o["clave_origen"] for o in ordenadas] == ["OC-A", "OC-B"]
    assert oc_en_curso(ordenadas[0], hoy)


def test_legajo_lista_ocs_vence_durante_y_vencido_antes(cliente_api, tenant_de_prueba, sesion):
    """Licencia que vence en la OC en curso y ya está vencida al inicio de otra OC futura."""
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "persona_ocs", "persona")
    req = insertar_definicion(sesion, t.tenant_id, "Licencia de conducir", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    insertar_documento(sesion, t.tenant_id, "persona_ocs", req, date(2026, 1, 1), date(2026, 10, 23))
    insertar_oc(sesion, t.tenant_id, "OC-CURSO", clave, date(2026, 9, 28), date(2026, 11, 2))
    insertar_oc(sesion, t.tenant_id, "OC-PLAN", clave, date(2026, 10, 25), date(2026, 11, 10))
    sesion.commit()

    r = cliente_api.get(
        "/v1/consultas/legajo",
        params={"sujeto_id": "persona_ocs"},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    doc = next(d for d in r.json()["documentos"] if d.get("requisito") == "Licencia de conducir")
    claves = [o["clave_origen"] for o in doc["ocs_afectadas"]]
    assert claves.index("OC-CURSO") < claves.index("OC-PLAN")
    assert "OC-CURSO" in claves
    assert "OC-PLAN" in claves
