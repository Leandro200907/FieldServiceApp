"""E-101: ficha legajo — tarjetas, estado_fila, registro con respaldo (GET /v1/consultas/legajo)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.comun.reloj import hoy_del_tenant
from tests import apoyo_e97
from tests.test_comandos_legajos import _alta_persona, _cargar, _ok, _post
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
from tests.test_validacion_evidencia import _validar
from app.comun.reloj import ahora_utc

pytest_plugins = ("tests.test_orquestacion",)


def _induccion_en_legajo(body: dict, nombre: str) -> dict:
    return next(i for i in body["inducciones"] if nombre in (i.get("requisito") or ""))


def _competencia_en_legajo(body: dict, nombre: str) -> dict:
    return next(i for i in body["acreditaciones"] if nombre in (i.get("requisito") or ""))


def test_e101_legado_apto_sin_certificado_tarjeta_y_fila(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e101", "empresa")
    persona = "persona-e101-legacy"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    req_doc = insertar_definicion(sesion, t.tenant_id, "Apto E101", "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción E101 legacy", "l": loc_id},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_doc: "bloqueante_duro", req_ind: "bloqueante_duro"})
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
    from tests import apoyo

    apoyo.respaldo_valido_en_documento(sesion, t.tenant_id, doc_apto)
    sesion.execute(
        text(
            "INSERT INTO modulo1.documento_soporte (tenant_id, documento_id, soporte_documento_id, es_certificado_propio) "
            "VALUES (:t, CAST(:ind AS uuid), CAST(:ap AS uuid), false)"
        ),
        {"t": t.tenant_id, "ind": ind_id, "ap": doc_apto},
    )
    insertar_oc(sesion, t.tenant_id, "OC-E101-LEG", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    body = _legajo(cliente_api, t, persona).json()
    res = body["resumen"]
    assert res["exigidos_sin_documento"] >= 1
    assert res["exigidos_vencidos"] == 0
    fila = _induccion_en_legajo(body, "Inducción E101")
    assert fila["estado_fila"] == "Sin respaldo válido"
    assert fila.get("gestion_responsable") == "registrar_induccion"
    assert "Sin archivo de respaldo" not in str(fila.get("estados_adicionales") or [])


def test_e101_certificado_pendiente_calendario_no_en_regla(cliente_api, tenant_de_prueba, sesion, storage):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e101p", "empresa")
    persona = "persona-e101-pend"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción E101 pend", "l": loc_id},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_ind: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-E101-PEND", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    cert_id = apoyo_e97.certificado_subido(cliente_api, storage, t, persona, validar=False)
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_induccion",
            {
                "persona_id": persona,
                "locacion_id": loc_id,
                "requisito_definicion_id": req_ind,
                "vigente_desde": (hoy - timedelta(days=10)).isoformat(),
                "vigente_hasta": (hoy + timedelta(days=200)).isoformat(),
                "certificado_documento_id": cert_id,
            },
        )
    )

    body = _legajo(cliente_api, t, persona).json()
    assert body["resumen"]["en_regla_exigidos"] == 0
    assert body["resumen"]["exigidos_vencidos"] == 0
    assert body["resumen"]["exigidos_vigentes"] >= 1
    fila = _induccion_en_legajo(body, "Inducción E101 pend")
    assert fila["estado_fila"] == "Pendiente de validación"
    assert not fila.get("gestion_responsable")


def test_e101_certificado_valido_fila_y_certificado_id(cliente_api, tenant_de_prueba, sesion, storage):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e101v", "empresa")
    persona = "persona-e101-val"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción E101 val", "l": loc_id},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_ind: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-E101-VAL", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    cert_id = apoyo_e97.certificado_subido(cliente_api, storage, t, persona, validar=False)
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_induccion",
            {
                "persona_id": persona,
                "locacion_id": loc_id,
                "requisito_definicion_id": req_ind,
                "vigente_desde": (hoy - timedelta(days=10)).isoformat(),
                "vigente_hasta": (hoy + timedelta(days=200)).isoformat(),
                "certificado_documento_id": cert_id,
            },
        )
    )
    _validar(t, storage, ahora=ahora_utc())

    body = _legajo(cliente_api, t, persona).json()
    assert body["resumen"]["en_regla_exigidos"] == 1
    fila = _induccion_en_legajo(body, "Inducción E101 val")
    assert fila["estado_fila"] == "Vigente"
    assert fila["certificado_respaldo_documento_id"] == cert_id
    assert "sin_archivo_respaldo" not in (fila.get("estados_adicionales") or [])


def test_e101_certificado_invalido_sin_documento_y_boton(cliente_api, tenant_de_prueba, sesion, storage):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e101i", "empresa")
    persona = "persona-e101-inv"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    loc_id = clave["l"]
    req_comp = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
                "VALUES (:t, :n, 'competencia', 'persona') RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Competencia E101 inv"},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_comp: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-E101-INV", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    cert_id = apoyo_e97.certificado_subido(cliente_api, storage, t, persona, validar=False)
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_acreditacion_de_competencia",
            {
                "persona_id": persona,
                "requisito_definicion_id": req_comp,
                "vigente_desde": (hoy - timedelta(days=10)).isoformat(),
                "vigente_hasta": (hoy + timedelta(days=200)).isoformat(),
                "certificado_documento_id": cert_id,
            },
        )
    )
    from app.db import tenant_session

    with tenant_session(t.tenant_id) as s:
        s.execute(
            text(
                "UPDATE modulo1.documento SET archivo_validacion = 'invalido' WHERE documento_id = CAST(:d AS uuid)"
            ),
            {"d": cert_id},
        )
        s.commit()

    body = _legajo(cliente_api, t, persona).json()
    assert body["resumen"]["exigidos_sin_documento"] >= 1
    fila = _competencia_en_legajo(body, "Competencia E101 inv")
    assert fila["estado_fila"] == "Sin respaldo válido"
    assert fila.get("gestion_responsable") == "registrar_acreditacion"


def test_e101_ambito_nombre_legible(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    persona = _alta_persona(cliente_api, t, "DNI-E101-AMB")
    loc_id = clave["l"]
    nombre_loc = sesion.execute(
        text("SELECT nombre FROM modulo1.locacion_oc WHERE locacion_id = CAST(:l AS uuid)"),
        {"l": loc_id},
    ).scalar()
    req_ind = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción E101 ámbito", "l": loc_id},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_ind: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-E101-AMB", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    body = _legajo(cliente_api, t, persona).json()
    fila = _induccion_en_legajo(body, "Inducción E101 ámbito")
    assert fila.get("ambito_nombre") == nombre_loc
    assert fila.get("locacion_nombre") == nombre_loc
