"""Plantilla pública XLSX: columna Observación libre y Control solo en Excel."""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar
from tests.test_operadoras_documentales import _ENCABEZADOS, _alta_operadora, _xlsx

_PLANTILLA = Path(__file__).resolve().parents[2] / "frontend" / "public" / "Plantilla_presentaciones_operadoras.xlsx"


def test_plantilla_observacion_sin_formulas():
    wb = load_workbook(_PLANTILLA, data_only=False)
    hoja = wb["Presentaciones"]
    assert hoja["N5"].value == "Observación"
    assert hoja["O5"].value == "Control"
    for fila in range(6, 51):
        celda = hoja[f"N{fila}"]
        assert celda.data_type != "f", f"N{fila} no debe tener fórmula"
        assert not (isinstance(celda.value, str) and celda.value.startswith("="))
        assert hoja[f"O{fila}"].data_type == "f"


def test_observacion_con_texto_de_control_no_se_persiste(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Plantilla")
    req = _alta_def(cliente_api, t, "Apto plantilla ctrl")
    p = _alta_persona(cliente_api, t, "persona_plantilla_ctrl")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op Plantilla", "persona", "persona_plantilla_ctrl", p, "Apto plantilla ctrl", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", "Faltan campos obligatorios"],
    ]
    headers = {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    r = cliente_api.post("/v1/comandos/importar_planilla_operadoras", content=_xlsx(filas), headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["filas_aceptadas"] == 1
    with tenant_session(t.tenant_id) as session:
        obs = session.execute(
            text(
                "SELECT observacion FROM modulo1.movimiento_entrega_operadora "
                "WHERE documento_id = :d ORDER BY paso_en DESC LIMIT 1"
            ),
            {"d": doc["documento_id"]},
        ).scalar_one()
    assert obs is None
