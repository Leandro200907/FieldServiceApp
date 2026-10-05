"""E-97: certificado propio para inducción/competencia (registro y lectura D19)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.core.orquestacion import evaluar_compromiso
from app.db import tenant_session
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_catalogos_maestros,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    requisitos_de,
    sesion,  # noqa: F401
)
from tests.test_storage import _subir_completo
from tests.test_validacion_evidencia import _validar

pytest_plugins = ("tests.test_orquestacion",)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _certificado_subido(cliente_api, storage, tenant, persona_id: str, *, validar: bool = True) -> str:
    cert = _ok(
        _post(
            cliente_api,
            tenant,
            "responsable_legajos",
            "crear_certificado_respaldo",
            {"persona_id": persona_id},
        )
    )
    cert_id = cert["certificado_documento_id"]
    _subir_completo(cliente_api, storage, tenant, cert_id, validar=validar)
    return cert_id


def test_e97_apto_como_certificado_rechazado(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    loc = str(__import__("uuid").uuid4())
    req_doc = _alta_def(cliente_api, t, "Apto E97 neg")
    req_ind = _alta_def(cliente_api, t, "Inducción E97 neg", "induccion", locacion_id=loc)
    persona = _alta_persona(cliente_api, t, "DNI-E97-NEG")
    doc_apto = _cargar(cliente_api, t, persona, req_doc, solo_declarado=True)["documento_id"]
    with tenant_session(t.tenant_id) as s:
        hoy = hoy_del_tenant(s, t.tenant_id)
    r = _post(
        cliente_api,
        t,
        "responsable_legajos",
        "registrar_induccion",
        {
            "persona_id": persona,
            "locacion_id": loc,
            "requisito_definicion_id": req_ind,
            "vigente_desde": (hoy - timedelta(days=30)).isoformat(),
            "vigente_hasta": (hoy + timedelta(days=365)).isoformat(),
            "certificado_documento_id": doc_apto,
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["codigo"] == "respaldo_tipo_no_admitido"


def test_e97_induccion_flujo_certificado_pendiente_luego_en_regla(cliente_api, tenant_de_prueba, sesion, storage):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e97", "empresa")
    persona = "persona-e97-lucia"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción HSE E97", "l": loc_id},
        ).scalar()
    )
    insertar_matriz(sesion, t.tenant_id, clave, {req_ind: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-E97-LU", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    cert_id = _certificado_subido(cliente_api, storage, t, persona, validar=False)
    desde = (hoy - timedelta(days=10)).isoformat()
    hasta = (hoy + timedelta(days=200)).isoformat()
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
                "vigente_desde": desde,
                "vigente_hasta": hasta,
                "certificado_documento_id": cert_id,
            },
        )
    )
    ind_id = reg["induccion_id"]

    legajo = cliente_api.get(
        "/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("responsable_legajos")
    )
    assert legajo.json()["resumen"]["en_regla_exigidos"] == 0

    with tenant_session(t.tenant_id) as s_motor:
        r_motor = evaluar_compromiso(s_motor, t.tenant_id, "OC-E97-LU", AHORA, None)
    assert requisitos_de(r_motor, persona)[req_ind]["veredicto"] == "requiere_revision"

    _validar(t, storage, ahora=ahora_utc())

    with tenant_session(t.tenant_id) as s:
        conf = s.execute(
            text("SELECT estado_confirmacion FROM modulo1.documento WHERE documento_id = CAST(:d AS uuid)"),
            {"d": ind_id},
        ).scalar()
        assert conf == "verificado"

    legajo2 = cliente_api.get(
        "/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("responsable_legajos")
    )
    assert legajo2.json()["resumen"]["en_regla_exigidos"] == 1

    with tenant_session(t.tenant_id) as s_motor:
        r_motor2 = evaluar_compromiso(s_motor, t.tenant_id, "OC-E97-LU", AHORA, None)
    assert requisitos_de(r_motor2, persona)[req_ind]["veredicto"] == "habilitado"


def test_e97_lectura_induccion_vieja_con_apto_no_habilita(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    clave = clave_de_matriz()
    insertar_catalogos_maestros(sesion, t.tenant_id, clave)
    insertar_legajo(sesion, t.tenant_id, "empresa_e97_leg", "empresa")
    persona = "persona-e97-legacy"
    insertar_legajo(sesion, t.tenant_id, persona, "persona")
    req_doc = insertar_definicion(sesion, t.tenant_id, "Apto legacy E97", "persona")
    loc_id = clave["l"]
    req_ind = str(
        sesion.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id) "
                "VALUES (:t, :n, 'induccion', 'persona', CAST(:l AS uuid)) RETURNING requisito_definicion_id"
            ),
            {"t": t.tenant_id, "n": "Inducción legacy", "l": loc_id},
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
    apoyo.respaldo_valido_en_documento(sesion, t.tenant_id, doc_apto)
    sesion.execute(
        text("UPDATE modulo1.documento SET estado_confirmacion = 'verificado' WHERE documento_id = CAST(:d AS uuid)"),
        {"d": ind_id},
    )
    sesion.execute(
        text(
            "INSERT INTO modulo1.documento_soporte (tenant_id, documento_id, soporte_documento_id, es_certificado_propio) "
            "VALUES (:t, CAST(:ind AS uuid), CAST(:ap AS uuid), false)"
        ),
        {"t": t.tenant_id, "ind": ind_id, "ap": doc_apto},
    )
    insertar_oc(sesion, t.tenant_id, "OC-E97-LEG", clave, hoy, hoy + timedelta(days=30))
    sesion.commit()

    with tenant_session(t.tenant_id) as s_motor:
        r_motor = evaluar_compromiso(s_motor, t.tenant_id, "OC-E97-LEG", AHORA, None)
    assert requisitos_de(r_motor, persona)[req_ind]["veredicto"] == "requiere_revision"
