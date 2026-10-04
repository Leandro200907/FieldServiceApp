"""E-29 / E-30: idempotencia de importación y fecha no informada en espejo."""
from __future__ import annotations

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_operadoras_documentales import _ENCABEZADOS, _alta_operadora, _xlsx


def test_reimportar_misma_fila_planilla_no_duplica_movimiento_ni_evento(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Idem Fila")
    req = _alta_def(cliente_api, t, "Apto idem fila")
    sujeto = _alta_persona(cliente_api, t, "persona_idem_fila")
    doc = _cargar(cliente_api, t, sujeto, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        [
            "Op Idem Fila", "persona", "persona_idem_fila", sujeto, "Apto idem fila", req, "",
            "2026-09-27", "2027-09-25", "enviado", "", "2026-09-27T11:00:00+00:00", "", "",
        ],
    ]
    xlsx = _xlsx(filas)
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "X-Nombre-Archivo": "reimport.xlsx",
    }
    assert cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=xlsx, headers=headers).status_code == 200
    assert cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=xlsx, headers=headers).status_code == 200
    with tenant_session(t.tenant_id) as session:
        movs = session.execute(
            text("SELECT count(*) FROM modulo1.movimiento_entrega_operadora WHERE documento_id = :d"),
            {"d": doc["documento_id"]},
        ).scalar_one()
        eventos = session.execute(
            text(
                "SELECT count(*) FROM modulo1.event_log "
                "WHERE tenant_id = :t AND tipo = 'EstadoDocumentoOperadoraRegistrado' "
                "AND payload->>'documento_id' = :d"
            ),
            {"t": t.tenant_id, "d": doc["documento_id"]},
        ).scalar_one()
    assert movs == 1
    assert eventos == 1


def test_rechazo_sin_fecha_respuesta_muestra_fecha_no_informada(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto sin fecha op")
    sujeto = _alta_persona(cliente_api, t, "persona_sin_fecha_op")
    doc = _cargar(cliente_api, t, sujeto, req, desde="2026-03-01", hasta="2027-03-01")
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_estado_documento_operadora",
            {
                "operadora": "YPF",
                "sujeto_id": sujeto,
                "documento_id": doc["documento_id"],
                "estado": "rechazado",
                "observacion": "Sin fecha en planilla",
            },
        )
    )
    with tenant_session(t.tenant_id) as session:
        operadora_id = session.execute(
            text("SELECT operadora_id::text FROM modulo1.operadora_documental WHERE lower(nombre) = 'ypf'")
        ).scalar_one()
        requisito_id = session.execute(
            text("SELECT requisito_definicion_id::text FROM modulo1.documento WHERE documento_id = :d"),
            {"d": doc["documento_id"]},
        ).scalar_one()
    resp = cliente_api.get(
        "/v1/consultas/historial_operadora",
        headers=t.headers("responsable_legajos"),
        params={
            "operadora_id": operadora_id,
            "sujeto_id": sujeto,
            "requisito_definicion_id": requisito_id,
        },
    )
    assert resp.status_code == 200
    paso = resp.json()["versiones"][0]["pasos"][0]
    assert paso["estado"] == "rechazado"
    assert paso["paso_en"] == "fecha no informada"
