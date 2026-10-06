"""D19: habilitación exige confirmación y respaldo válido (motor, radar, acciones, paquete)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text

from app.core.estado_documental import EstadoRequisitoDocumental
from app.core.orquestacion import evaluar_compromiso
from app.db import tenant_session
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    requisitos_de,
    sesion,  # noqa: F401
)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _armar_oc(sesion, t, persona: str, req: str, clave_oc: str):
    insertar_legajo(sesion, t.tenant_id, "empresa_x", "empresa")
    clave = clave_de_matriz()
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, clave_oc, clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    with tenant_session(t.tenant_id) as s:
        oc_id = s.execute(text("SELECT oc_id FROM modulo1.oc WHERE clave_origen = :c"), {"c": clave_oc}).scalar()
    return str(oc_id)


def test_d19_verificado_sin_archivo_no_habilita_en_motor_radar_acciones_y_paquete(
    cliente_api, tenant_de_prueba, sesion
):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "ART D19")
    persona = _alta_persona(cliente_api, t, "DNI-D19-A", t.sujeto_tecnico)
    doc_id = _cargar(cliente_api, t, persona, req, desde="2026-01-01", hasta="2027-12-31", solo_declarado=True)["documento_id"]
    with tenant_session(t.tenant_id) as s:
        s.execute(
            text("UPDATE modulo1.documento SET estado_confirmacion = 'verificado' WHERE documento_id = CAST(:d AS uuid)"),
            {"d": doc_id},
        )
    clave_oc = f"OC-D19-{uuid.uuid4().hex[:6]}"
    oc_id = _armar_oc(sesion, t, persona, req, clave_oc)

    with tenant_session(t.tenant_id) as s_motor:
        r_motor = evaluar_compromiso(s_motor, t.tenant_id, clave_oc, AHORA, None)
    assert requisitos_de(r_motor, persona)[req]["veredicto"] == "requiere_revision"

    r_radar = cliente_api.get(
        f"/v1/consultas/radar_documental_oc/{oc_id}/legajos/{persona}",
        headers=t.headers("responsable_legajos"),
    )
    estados = {x["nombre"]: x["estado"] for x in r_radar.json()["legajo"]["requisitos"]}
    assert estados["ART D19"] == EstadoRequisitoDocumental.PENDIENTE_REVISION.value

    r_acc = cliente_api.get(
        "/v1/consultas/acciones_pendientes",
        params={"mes": "2026-10", "limit": 100},
        headers=t.headers("responsable_legajos"),
    )
    assert any(a["requisito"] == "ART D19" and a["legajo_id"] == persona for a in r_acc.json()["items"])

    paq = _ok(
        cliente_api.post(
            "/v1/comandos/generar_paquete_entrega",
            headers=t.headers("responsable_legajos"),
            json={"sujeto_id": persona, "dias_validez": 7},
        )
    )
    token = paq["url"].rsplit("/", 1)[-1]
    pub = cliente_api.get(f"/v1/publico/paquete/{token}")
    assert pub.status_code == 200
    fila = next(r for r in pub.json()["requisitos"] if r["requisito"] == "ART D19")
    assert fila["estado"] == "pendiente_de_revision"


def test_d19_competencia_con_soporte_valido_habilita(cliente_api, tenant_de_prueba, sesion, storage):
    t = tenant_de_prueba
    loc = str(uuid.uuid4())
    req_comp = _alta_def(cliente_api, t, "Altura D19", categoria="competencia")
    persona = _alta_persona(cliente_api, t, "DNI-D19-B", t.sujeto_tecnico)
    from tests.apoyo_e97 import certificado_subido

    cert_id = certificado_subido(cliente_api, storage, t, persona)
    acr = _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_acreditacion_de_competencia",
            {
                "persona_id": persona,
                "requisito_definicion_id": req_comp,
                "vigente_desde": "2026-01-01",
                "vigente_hasta": "2027-12-31",
                "certificado_documento_id": cert_id,
            },
        )
    )
    clave_oc = f"OC-D19C-{uuid.uuid4().hex[:6]}"
    with tenant_session(t.tenant_id) as s:
        clave = clave_de_matriz()
        insertar_matriz(s, t.tenant_id, clave, {req_comp: "bloqueante_duro"})
        insertar_oc(s, t.tenant_id, clave_oc, clave, date(2026, 10, 1), date(2026, 10, 5))
        s.commit()
    with tenant_session(t.tenant_id) as s_motor:
        r_motor = evaluar_compromiso(s_motor, t.tenant_id, clave_oc, AHORA, None)
    assert requisitos_de(r_motor, persona)[req_comp]["veredicto"] == "habilitado"
    assert acr["acreditacion_id"]


def test_d19_confirmar_sin_respaldo_rechazado(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Confirm D19")
    persona = _alta_persona(cliente_api, t, "DNI-D19-C")
    doc_id = _cargar(cliente_api, t, persona, req, solo_declarado=True)["documento_id"]
    r = _post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": doc_id})
    assert r.status_code == 422
    assert r.json()["error"]["codigo"] == "sin_respaldo_valido"


def test_d19_declarado_archivo_pendiente_no_cuenta_en_resumen_legajo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia D19 resumen")
    persona = _alta_persona(cliente_api, t, "DNI-D19-RES", t.sujeto_tecnico)
    doc_id = _cargar(
        cliente_api, t, persona, req, desde="2026-01-01", hasta="2027-12-31", solo_declarado=True
    )["documento_id"]
    with tenant_session(t.tenant_id) as s:
        s.execute(
            text(
                "UPDATE modulo1.documento SET archivo_estado = 'confirmado', archivo_validacion = 'pendiente', "
                "clave_storage = :c, checksum_archivo = 'x', archivo_bytes = 1 WHERE documento_id = CAST(:d AS uuid)"
            ),
            {"d": doc_id, "c": f"{t.tenant_id}/{doc_id}/pendiente.pdf"},
        )
    r = cliente_api.get(
        "/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("responsable_legajos")
    )
    assert r.status_code == 200, r.text
    assert r.json()["resumen"]["vigentes_hoy"] == 0


def test_d19_timeline_seguro_verificado_sin_archivo_no_verde(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    insertar_legajo(sesion, t.tenant_id, "empresa_rc", "empresa")
    req = insertar_definicion(sesion, t.tenant_id, "Seguro RC", "empresa")
    insertar_documento(
        sesion, t.tenant_id, "empresa_rc", req, date(2026, 1, 1), date(2027, 12, 31), confirmacion="declarado"
    )
    sesion.commit()
    r = cliente_api.get(
        "/v1/consultas/timeline_recursos",
        params={"desde": "2026-10-01", "hasta": "2026-11-30", "tipo_sujeto": "empresa"},
        headers=t.headers("responsable_legajos"),
    )
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["sujeto_id"] == "empresa_rc")
    tramo = next(t for t in item["tramos"] if t["requisito"] == "Seguro RC")
    assert tramo["estado_visual"] == "declarado_sin_verificar"


def test_d19_importar_lote_sigue_declarado(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Planilla D19")
    persona = _alta_persona(cliente_api, t, "DNI-D19-D")
    lote = str(uuid.uuid4())
    r = _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "importar_lote",
            {
                "lote_id": lote,
                "filas": [
                    {
                        "sujeto_id": persona,
                        "requisito_definicion_id": req,
                        "vigente_desde": "2026-01-01",
                        "vigente_hasta": "2027-06-30",
                    }
                ],
            },
        )
    )
    assert r["filas_aceptadas"] == 1
    with tenant_session(t.tenant_id) as s:
        conf = s.execute(
            text(
                "SELECT estado_confirmacion FROM modulo1.documento WHERE sujeto_id = :s AND requisito_definicion_id = CAST(:r AS uuid)"
            ),
            {"s": persona, "r": req},
        ).scalar()
    assert conf == "declarado"
