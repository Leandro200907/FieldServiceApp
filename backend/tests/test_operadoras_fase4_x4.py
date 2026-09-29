"""Fase 4 X-4: fechas con hora de la planilla se interpretan en la zona del tenant."""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar
from tests.test_operadoras_documentales import _ENCABEZADOS, _xlsx

_TZ = "America/Argentina/Buenos_Aires"


def test_fecha_exportacion_sin_zona_usa_medianoche_local(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto tz")
    p = _alta_persona(cliente_api, t, "persona_tz_x4")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op TZ", "persona", "persona_tz_x4", p, "Apto tz", req,
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27", "", "", ""],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    with tenant_session(t.tenant_id) as session:
        exportado = session.execute(
            text("SELECT exportado_en FROM modulo1.entrega_documento_operadora WHERE documento_id = :d"),
            {"d": doc["documento_id"]},
        ).scalar_one()
    local = exportado.astimezone(ZoneInfo(_TZ))
    assert local.date() == date(2026, 9, 27)
    assert local.hour == 0 and local.minute == 0
