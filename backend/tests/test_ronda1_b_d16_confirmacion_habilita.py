"""D16: documento sin confirmar no habilita; con confirmada anterior se evalúa esa."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text

from app.core.estado_documental import EstadoRequisitoDocumental
from app.core.orquestacion import evaluar_compromiso
from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    requisitos_de,
    sesion,  # noqa: F401
)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _armar_oc(cliente_api, tenant_de_prueba, sesion, persona: str, req: str, clave_oc: str):
    t = tenant_de_prueba
    insertar_legajo(sesion, t.tenant_id, "empresa_x", "empresa")
    clave = clave_de_matriz()
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, clave_oc, clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.commit()
    with tenant_session(t.tenant_id) as s:
        oc_id = s.execute(
            text("SELECT oc_id FROM modulo1.oc WHERE clave_origen = :c"),
            {"c": clave_oc},
        ).scalar()
    return t, str(oc_id)


def test_d16_confirmada_con_propuesta_radar_vencimientos_acciones_y_motor(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia D16")
    persona = _alta_persona(cliente_api, t, "DNI-D16-A", t.sujeto_tecnico)
    v1_hasta = "2026-12-31"
    _cargar(cliente_api, t, persona, req, desde="2026-09-01", hasta=v1_hasta)
    _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2027-01-01",
                "vigente_hasta": "2028-01-01",
            },
        )
    )
    clave_oc = f"OC-D16-{uuid.uuid4().hex[:6]}"
    t, oc_id = _armar_oc(cliente_api, tenant_de_prueba, sesion, persona, req, clave_oc)

    r_leg = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("responsable_legajos"))
    doc = next(d for d in r_leg.json()["documentos"] if d["requisito_definicion_id"] == req)
    assert doc["vigente_hasta"] == v1_hasta
    assert doc.get("propuesta_en_revision") is not None

    r_venc = cliente_api.get("/v1/consultas/tablero_vencimientos", params={"dias": 400}, headers=t.headers("responsable_legajos"))
    fila_v = next(i for i in r_venc.json()["items"] if i["requisito_definicion_id"] == req and i["sujeto_id"] == persona)
    assert fila_v["vigente_hasta"] == v1_hasta

    r_radar = cliente_api.get(
        f"/v1/consultas/radar_documental_oc/{oc_id}/legajos/{persona}",
        headers=t.headers("responsable_legajos"),
    )
    estados = {x["nombre"]: x["estado"] for x in r_radar.json()["legajo"]["requisitos"]}
    assert estados["Licencia D16"] == EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO.value

    r_acc = cliente_api.get(
        "/v1/consultas/acciones_pendientes",
        params={"mes": "2026-10", "limit": 100},
        headers=t.headers("responsable_legajos"),
    )
    acc_reqs = {a["requisito"] for a in r_acc.json()["items"] if a["legajo_id"] == persona}
    assert "Licencia D16" not in acc_reqs

    with tenant_session(t.tenant_id) as s_motor:
        r_motor = evaluar_compromiso(s_motor, t.tenant_id, clave_oc, AHORA, None)
    assert requisitos_de(r_motor, persona)[req]["veredicto"] == "habilitado"


def test_d16_propuesta_unica_no_cumple_en_ningun_camino(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Solo propuesta D16")
    persona = _alta_persona(cliente_api, t, "DNI-D16-B", t.sujeto_tecnico)
    _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2026-09-01",
                "vigente_hasta": "2027-09-01",
            },
        )
    )
    clave_oc = f"OC-D16S-{uuid.uuid4().hex[:6]}"
    t, oc_id = _armar_oc(cliente_api, tenant_de_prueba, sesion, persona, req, clave_oc)

    r_leg = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": persona}, headers=t.headers("responsable_legajos"))
    doc = next(d for d in r_leg.json()["documentos"] if d["requisito_definicion_id"] == req)
    assert doc["estado_presentacion"] == "propuesta_en_revision"

    r_radar = cliente_api.get(
        f"/v1/consultas/radar_documental_oc/{oc_id}/legajos/{persona}",
        headers=t.headers("responsable_legajos"),
    )
    estados = {x["nombre"]: x["estado"] for x in r_radar.json()["legajo"]["requisitos"]}
    assert estados["Solo propuesta D16"] == EstadoRequisitoDocumental.PENDIENTE_REVISION.value
    assert estados["Solo propuesta D16"] != EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO.value

    with tenant_session(t.tenant_id) as s_motor:
        r_motor = evaluar_compromiso(s_motor, t.tenant_id, clave_oc, AHORA, None)
    assert requisitos_de(r_motor, persona)[req]["veredicto"] == "requiere_revision"
