"""E-105: textos de observacion_ficha en la ficha de legajo."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from app.comun.reloj import hoy_del_tenant
from tests import apoyo
from tests.test_comandos_legajos import _alta_persona
from tests.test_e101_ficha_legajo_respaldo import _competencia_en_legajo, _induccion_en_legajo
from tests.test_e91_flujo_legajo import _legajo
from tests.test_operadoras_documentales import _registrar
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


def test_e105_vigente_observacion_guion(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e105v", "empresa")
    persona = _alta_persona(cliente_api, t, "DNI-E105-V")
    req = insertar_definicion(sesion, t.tenant_id, "Apto E105 vigente", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    doc = insertar_documento(sesion, t.tenant_id, persona, req, hoy, hoy + timedelta(days=365))
    insertar_oc(sesion, t.tenant_id, "OC-E105-V", clave, hoy, hoy + timedelta(days=30))
    apoyo.respaldo_valido_en_documento(sesion, t.tenant_id, doc)
    sesion.commit()

    body = _legajo(cliente_api, t, persona).json()
    fila = next(d for d in body["documentos"] if d["requisito_definicion_id"] == req)
    assert fila["estado_fila"] == "Vigente"
    assert fila["observacion_ficha"] == "—"
    assert "confirmada y vigente" not in fila["observacion_ficha"]


def test_e105_rechazo_operadora_sin_frase_vigente(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e105r", "empresa")
    persona = _alta_persona(cliente_api, t, "DNI-E105-R")
    req = insertar_definicion(sesion, t.tenant_id, "Apto E105 rechazo", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    doc = insertar_documento(sesion, t.tenant_id, persona, req, hoy, hoy + timedelta(days=365))
    insertar_oc(sesion, t.tenant_id, "OC-E105-R", clave, hoy, hoy + timedelta(days=30))
    apoyo.respaldo_valido_en_documento(sesion, t.tenant_id, doc)
    sesion.commit()
    _registrar(
        cliente_api,
        t,
        sujeto_id=persona,
        documento_id=doc,
        estado="rechazado",
        rechazado_en="2026-02-03T10:00:00Z",
        observacion="No cumple",
    )

    body = _legajo(cliente_api, t, persona).json()
    fila = next(d for d in body["documentos"] if d["id"] == doc)
    assert fila.get("observacion_operadora", "").startswith("Rechazado por")
    assert fila["observacion_ficha"] == "—"
    assert "confirmada y vigente" not in (fila.get("observacion_ficha") or "")


def test_e105_sin_respaldo_motivo_por_categoria(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e105s", "empresa")
    persona = "persona-e105-sin-resp"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    req_doc = insertar_definicion(sesion, t.tenant_id, "Apto E105 soporte", "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción E105 sin respaldo", "l": loc_id},
        ).scalar()
    )
    req_comp = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
                "VALUES (:t, :n, 'competencia', 'persona') RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Competencia E105 sin respaldo"},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_doc: "bloqueante_duro", req_ind: "bloqueante_duro", req_comp: "bloqueante_duro"})
    doc_apto = insertar_documento(sesion, t.tenant_id, persona, req_doc, hoy, hoy + timedelta(days=365))
    ind_id = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id, locacion_id, "
                "vigente_desde, vigente_hasta, estado_confirmacion, origen) "
                "VALUES (:t, :s, CAST(:r AS uuid), CAST(:l AS uuid), :d, :h, 'verificado', 'carga_manual') "
                "RETURNING documento_id"
            ),
            {"t": t.tenant_id, "s": persona, "r": req_ind, "l": loc_id, "d": hoy, "h": hoy + timedelta(days=365)},
        ).scalar()
    )
    comp_id = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id, "
                "vigente_desde, vigente_hasta, estado_confirmacion, origen) "
                "VALUES (:t, :s, CAST(:r AS uuid), :d, :h, 'verificado', 'carga_manual') "
                "RETURNING documento_id"
            ),
            {"t": t.tenant_id, "s": persona, "r": req_comp, "d": hoy, "h": hoy + timedelta(days=365)},
        ).scalar()
    )
    from tests import apoyo

    apoyo.respaldo_valido_en_documento(sesion, t.tenant_id, doc_apto)
    for padre in (ind_id, comp_id):
        sesion.execute(
            text(
                "INSERT INTO modulo1.documento_soporte (tenant_id, documento_id, soporte_documento_id, es_certificado_propio) "
                "VALUES (:t, CAST(:padre AS uuid), CAST(:ap AS uuid), false)"
            ),
            {"t": t.tenant_id, "padre": padre, "ap": doc_apto},
        )
    insertar_oc(sesion, t.tenant_id, "OC-E105-S", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    body = _legajo(cliente_api, t, persona).json()
    fila_ind = _induccion_en_legajo(body, "Inducción E105")
    fila_comp = _competencia_en_legajo(body, "Competencia E105")
    assert "registrá la inducción con su certificado" in fila_ind["observacion_ficha"]
    assert "inducción o competencia" not in fila_ind["observacion_ficha"]
    assert "registrá la competencia con su certificado" in fila_comp["observacion_ficha"]
    assert "inducción o competencia" not in fila_comp["observacion_ficha"]
