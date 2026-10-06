"""E-94: tarjetas de exigidos por calendario del papel (no por cobertura / estado_peor)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.comun.reloj import hoy_del_tenant
from app.modules.consultas.requisitos_exigidos_legajo import (
    AgregadoRequisitoExigido,
    resumen_exigidos_backlog,
)
from tests.test_comandos_legajos import _ok, _post
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


def _ag(
    rid: str,
    *,
    sin_cobertura: bool = False,
    es_rechazo: bool = False,
    estado_peor: str = "faltante",
    evidencia_id: str | None = "doc-1",
    vigente_hasta: date | None = None,
    archivo_validacion: str | None = None,
) -> AgregadoRequisitoExigido:
    return AgregadoRequisitoExigido(
        requisito_definicion_id=rid,
        nombre=rid,
        categoria="documento",
        tipo="documento",
        estado_peor=estado_peor,
        evidencia_id=evidencia_id,
        vigente_hasta=vigente_hasta,
        archivo_validacion=archivo_validacion,
        sin_cobertura=sin_cobertura,
        es_rechazo_operadora=es_rechazo,
        operadora_nombre="Vista" if es_rechazo else None,
    )


def test_maria_apto_rechazo_faltante_con_evidencia_cuenta_vigente_en_tarjeta():
    """Forma real demo: E-10 deja estado faltante + evidencia_id; tarjeta sigue el calendario."""
    hoy = date(2026, 10, 5)
    plazo = 30
    mapa = {
        "r1": _ag("r1", evidencia_id="d1", vigente_hasta=hoy + timedelta(days=120)),
        "r2": _ag("r2", evidencia_id="d2", vigente_hasta=hoy + timedelta(days=120)),
        "r3": _ag("r3", evidencia_id="d3", vigente_hasta=hoy + timedelta(days=120)),
        "r4": _ag("r4", evidencia_id="d4", vigente_hasta=hoy + timedelta(days=120)),
        "r5": _ag(
            "r5",
            sin_cobertura=True,
            es_rechazo=True,
            estado_peor="faltante",
            evidencia_id="d5",
            vigente_hasta=hoy + timedelta(days=365),
        ),
    }
    res = resumen_exigidos_backlog(mapa, hoy, plazo)
    assert res["exigidos"] == 5
    assert res["en_regla_exigidos"] == 4
    assert res["observados_operadora"] == 1
    assert res["exigidos_vencidos"] == 0
    assert res["exigidos_por_vencer"] == 0
    assert res["exigidos_vigentes"] == 5
    assert res["exigidos_sin_documento"] == 0


def test_evidencia_invalida_sigue_en_tarjeta_vencidos():
    hoy = date(2026, 10, 5)
    mapa = {
        "r1": _ag(
            "r1",
            sin_cobertura=True,
            estado_peor="evidencia_invalida",
            evidencia_id="doc-1",
            vigente_hasta=hoy + timedelta(days=365),
            archivo_validacion="invalido",
        ),
    }
    res = resumen_exigidos_backlog(mapa, hoy, 30)
    assert res["exigidos_sin_documento"] == 1
    assert res["exigidos_vencidos"] == 0


def test_legajo_integracion_rechazo_vista_tarjetas_por_calendario(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave, operadora="Vista")
    persona = "persona-e94-maria"
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    req_art = insertar_definicion(sesion, t.tenant_id, "ART empresa E94", "empresa")
    nombres = ("Apto E94", "Licencia E94", "Inducción E94", "Competencia E94", "Constancia E94")
    reqs_persona = [insertar_definicion(sesion, t.tenant_id, n, "persona") for n in nombres]
    matriz = {req_art: "bloqueante_duro", **{r: "bloqueante_duro" for r in reqs_persona}}
    insertar_matriz(sesion, t.tenant_id, clave, matriz)
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_art, hoy, hoy + timedelta(days=365))
    doc_ids = []
    for r in reqs_persona:
        doc_ids.append(insertar_documento(sesion, t.tenant_id, persona, r, hoy, hoy + timedelta(days=365)))
    insertar_oc(sesion, t.tenant_id, "OC-E94-VISTA", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_estado_documento_operadora",
            {
                "operadora": "Vista",
                "sujeto_id": persona,
                "documento_id": doc_ids[0],
                "estado": "rechazado",
                "rechazado_en": f"{hoy.isoformat()}T12:00:00Z",
            },
        )
    )
    r = cliente_api.get(
        "/v1/consultas/legajo",
        params={"sujeto_id": persona},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    resumen = r.json()["resumen"]
    total = resumen["exigidos"]
    assert total == len(reqs_persona)
    assert resumen["en_regla_exigidos"] == total - 1
    assert resumen["observados_operadora"] == 1
    assert resumen["exigidos_vencidos"] == 0
    assert resumen["exigidos_vigentes"] == total
    assert resumen["exigidos_sin_documento"] == 0
