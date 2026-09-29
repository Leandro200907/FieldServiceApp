"""Fase 4 X-1: errores de celda/fila en planilla → 422, nunca 500."""
from __future__ import annotations

from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from tests.test_operadoras_documentales import _ENCABEZADOS, _xlsx


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


def _xlsx_fila_r_invalido() -> bytes:
    """Planilla mínima con fila de datos r=\"x2\" (no se puede parchear el ZIP comprimido)."""
    valores = [
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
        ["Op", "persona", "id1", "", "Apto", "", "999999999999", "2027-01-01", "exportado",
         "2026-01-01T00:00:00+00:00", "", "", ""],
    ]
    raw = _xlsx(filas)
    return raw.replace(
        b'<c r="G6" t="inlineStr"><is><t>999999999999</t></is></c>',
        b'<c r="G6"><v>999999999999</v></c>',
    )


def test_indice_shared_string_inexistente_devuelve_422(cliente_api, tenant_de_prueba):
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx_shared_string_indice_invalido(),
        headers=_headers(tenant_de_prueba),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["detalles"]["errores"][0]["fila"] == 6


def test_numero_fila_xml_invalido_devuelve_422(cliente_api, tenant_de_prueba):
    from app.modules.operadoras.lector_xlsx import leer_planilla

    filas, errores = leer_planilla(_xlsx_fila_r_invalido())
    assert not filas
    assert any(e.get("codigo") == "fila_invalida" for e in errores)
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx_fila_r_invalido(),
        headers=_headers(tenant_de_prueba),
    )
    assert r.status_code == 422, r.text


def test_fecha_serial_desbordada_devuelve_422(cliente_api, tenant_de_prueba):
    r = cliente_api.post(
        "/v1/comandos/importar_planilla_operadoras",
        content=_xlsx_fecha_serial_enorme(),
        headers=_headers(tenant_de_prueba),
    )
    assert r.status_code == 422, r.text
    assert any(e.get("fila") == 6 for e in r.json()["error"]["detalles"]["errores"])
