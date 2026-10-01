"""Fase 4 X-1: errores de celda/fila en planilla → 422, nunca 500."""
from __future__ import annotations

from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar
from tests.test_operadoras_documentales import _ENCABEZADOS, _alta_operadora, _xlsx


def _headers(t):
    return {
        **t.headers("responsable_legajos"),
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }


def _xlsx_shared_string_indice_invalido() -> bytes:
    contenido = BytesIO()
    with ZipFile(contenido, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")
        z.writestr("xl/sharedStrings.xml", """<?xml version="1.0"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="1" uniqueCount="1">
<si><t>Op</t></si></sst>""")
        z.writestr("xl/workbook.xml", """<?xml version="1.0"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Presentaciones" sheetId="1" r:id="rId1"/></sheets></workbook>""")
        z.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""")
        enc = "".join(f'<c r="{chr(64+i)}5" t="inlineStr"><is><t>{v}</t></is></c>' for i, v in enumerate(_ENCABEZADOS, 1))
        fila = '<c r="A6" t="s"><v>5</v></c><c r="B6" t="inlineStr"><is><t>persona</t></is></c>'
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="5">{enc}</row><row r="6">{fila}</row></sheetData></worksheet>',
        )
    return contenido.getvalue()


def _xlsx_fila_r_invalido(valores: list[object] | None = None) -> bytes:
    valores = valores or [
        "Operadora Norte", "persona", "id1", "", "Apto", "", "", "",
        "exportado", "2026-01-01T00:00:00+00:00", "", "", "",
    ]

    def celda(col: int, fila: int, valor: object) -> str:
        letras = ""
        n = col
        while n:
            n, resto = divmod(n - 1, 26)
            letras = chr(65 + resto) + letras
        return f'<c r="{letras}{fila}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>'

    enc = "".join(celda(i, 5, v) for i, v in enumerate(_ENCABEZADOS, 1))
    datos = "".join(celda(i, 6, v) for i, v in enumerate(valores, 1))
    contenido = BytesIO()
    with ZipFile(contenido, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")
        z.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Presentaciones" sheetId="1" r:id="rId1"/></sheets></workbook>""")
        z.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""")
        z.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="5">{enc}</row><row r="x2">{datos}</row></sheetData></worksheet>',
        )
    return contenido.getvalue()


def _xlsx_fecha_serial_enorme() -> bytes:
    filas = [
        _ENCABEZADOS,
        ["Op", "persona", "id1", "", "Apto", "", "", "999999999999", "2027-01-01", "exportado",
         "2026-01-01T00:00:00+00:00", "", "", ""],
    ]
    raw = _xlsx(filas)
    return raw.replace(
        b'<c r="H6" t="inlineStr"><is><t>999999999999</t></is></c>',
        b'<c r="H6"><v>999999999999</v></c>',
    )


def test_indice_shared_string_inexistente_devuelve_422(cliente_api, tenant_de_prueba):
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx_shared_string_indice_invalido(),
        headers=_headers(tenant_de_prueba),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["detalles"]["errores"][0]["fila"] == 6


def test_numero_fila_xml_invalido_registra_fila_util(cliente_api, tenant_de_prueba):
    from app.modules.operadoras.lector_xlsx import leer_planilla

    filas, errores = leer_planilla(_xlsx_fila_r_invalido())
    assert not filas
    assert any(e.get("codigo") == "fila_invalida" and e.get("fila") == 6 for e in errores)


def test_fila_r_invalida_mas_valida_no_devuelve_500(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Valida")
    req = _alta_def(cliente_api, t, "Apto x1 mix")
    p = _alta_persona(cliente_api, t, "persona_x1_mix")
    doc = _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op Valida", "persona", "persona_x1_mix", p, "Apto x1 mix", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
    ]
    xlsx_valida = _xlsx(filas)
    # Planilla combinada: encabezado + fila r=x2 (rechazada) + fila válida r=7
    def celda(col: int, fila: int, valor: object) -> str:
        letras = ""
        n = col
        while n:
            n, resto = divmod(n - 1, 26)
            letras = chr(65 + resto) + letras
        return f'<c r="{letras}{fila}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>'

    enc = "".join(celda(i, 5, v) for i, v in enumerate(_ENCABEZADOS, 1))
    invalida_vals = [
        "Operadora Norte", "persona", "persona_x1_mix", p, "Apto x1 mix", req, "",
        "2026-09-27", "2027-09-25", "exportado", "2026-09-27T11:00:00+00:00", "", "", "",
    ]
    valida_vals = filas[1]
    fila_x2 = "".join(celda(i, 6, v) for i, v in enumerate(invalida_vals, 1))
    fila_ok = "".join(celda(i, 7, v) for i, v in enumerate(valida_vals, 1))
    contenido = BytesIO()
    with ZipFile(contenido, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", xlsx_valida[xlsx_valida.find(b"[Content_Types]"):xlsx_valida.find(b"xl/workbook")])
        z.writestr("xl/workbook.xml", xlsx_valida[xlsx_valida.find(b"<workbook"):xlsx_valida.find(b"xl/_rels")])
        z.writestr("xl/_rels/workbook.xml.rels", xlsx_valida[xlsx_valida.find(b"<Relationships"):xlsx_valida.find(b"xl/worksheets")])
        z.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData><row r="5">{enc}</row><row r="x2">{fila_x2}</row><row r="7">{fila_ok}</row></sheetData></worksheet>',
        )
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=contenido.getvalue(),
        headers=_headers(t),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filas_aceptadas"] == 1 and body["filas_rechazadas"] == 1
    assert body["resultados"][0]["documento_id"] == doc["documento_id"]
    assert body["errores"][0]["codigo"] == "fila_invalida"
    assert body["errores"][0]["fila"] == 6


def test_fallo_al_validar_respuesta_hace_rollback(cliente_api, tenant_de_prueba, monkeypatch):
    t = tenant_de_prueba
    _alta_operadora(cliente_api, t, "Op Rollback")
    req = _alta_def(cliente_api, t, "Apto rollback")
    p = _alta_persona(cliente_api, t, "persona_rollback")
    _cargar(cliente_api, t, p, req, desde="2026-09-27", hasta="2027-09-25")
    filas = [
        _ENCABEZADOS,
        ["Op Rollback", "persona", "persona_rollback", p, "Apto rollback", req, "",
         "2026-09-27", "2027-09-25", "exportado", "2026-09-27T10:00:00+00:00", "", "", ""],
    ]
    from app.modules.operadoras import router as router_operadoras

    original = router_operadoras.ImportarPlanillaOperadorasResponse.model_validate
    intentos = {"n": 0}

    def _falla_validacion(payload):
        original(payload)
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise ValueError("validación forzada en test")

    monkeypatch.setattr(router_operadoras.ImportarPlanillaOperadorasResponse, "model_validate", _falla_validacion)
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx(filas),
        headers={**_headers(t), "Idempotency-Key": "rollback-x1-test"},
    )
    assert r.status_code == 500
    with tenant_session(t.tenant_id) as session:
        total = session.execute(text("SELECT count(*) FROM modulo1.movimiento_entrega_operadora")).scalar_one()
    assert total == 0
    r2 = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx(filas),
        headers={**_headers(t), "Idempotency-Key": "rollback-x1-test"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["filas_aceptadas"] == 1


def test_fecha_serial_desbordada_devuelve_422(cliente_api, tenant_de_prueba):
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx_fecha_serial_enorme(),
        headers=_headers(tenant_de_prueba),
    )
    assert r.status_code == 422, r.text
    assert any(e.get("fila") == 6 for e in r.json()["error"]["detalles"]["errores"])
