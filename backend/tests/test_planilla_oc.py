"""Importación HTTP de planilla XLSX de OC (lector propio, filas de Excel)."""
from __future__ import annotations

import uuid
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

pytest_plugins = ("tests.test_orquestacion",)

from tests.test_orquestacion import clave_de_matriz, insertar_catalogos_maestros


_ENCABEZADOS_OC = [
    "Clave OC", "Referencia", "Operadora", "Locación", "Tipo de servicio",
    "Vigencia desde", "Vigencia hasta", "Estado",
]


def _xlsx_oc(filas: list[list[object]], hoja: str = "OC") -> bytes:
    def celda(col: int, fila: int, valor: object) -> str:
        letras = ""
        n = col
        while n:
            n, resto = divmod(n - 1, 26)
            letras = chr(65 + resto) + letras
        return f'<c r="{letras}{fila}" t="inlineStr"><is><t>{escape(str(valor))}</t></is></c>'

    xml_filas = []
    for numero, valores in enumerate(filas, start=1):
        xml_filas.append(
            f'<row r="{numero}">' + "".join(celda(i, numero, v) for i, v in enumerate(valores, 1)) + "</row>"
        )
    contenido = BytesIO()
    with ZipFile(contenido, "w", ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")
        z.writestr("xl/workbook.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="{hoja}" sheetId="1" r:id="rId1"/></sheets></workbook>""")
        z.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""")
        z.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(xml_filas)
            + "</sheetData></worksheet>",
        )
    return contenido.getvalue()


def test_importar_planilla_oc_xlsx_tres_validas_una_operadora_inexistente(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_catalogos_maestros(
        sesion, t.tenant_id, clave,
        operadora="YPF", locacion="Loma La Lata", tipo_servicio="Wireline",
    )
    sesion.commit()
    filas = [
        _ENCABEZADOS_OC,
        ["OC-XLSX-1", "r1", "YPF", "Loma La Lata", "Wireline", "2026-10-01", "2026-10-10", "activo"],
        ["OC-XLSX-2", "r2", "YPF", "Loma La Lata", "Wireline", "2026-10-11", "2026-10-20", "activo"],
        ["OC-XLSX-3", "r3", "YPF", "Loma La Lata", "Wireline", "2026-10-21", "2026-10-31", "activo"],
        ["OC-XLSX-4", "r4", "Operadora Fantasma", "Loma La Lata", "Wireline", "2026-11-01", "2026-11-10", "activo"],
    ]
    lote = str(uuid.uuid4())
    r = cliente_api.post(
        f"/v1/comandos/importar_planilla_oc?lote_id={lote}",
        content=_xlsx_oc(filas),
        headers={
            **t.headers("responsable_legajos"),
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "X-Nombre-Archivo": "planilla_oc.xlsx",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filas_aceptadas"] == 3
    assert body["filas_rechazadas"] == 1
    rechazada = body["detalle_filas_rechazadas"][0]
    assert rechazada["indice"] == 5
    assert rechazada["clave_origen"] == "OC-XLSX-4"
    assert "operadora desconocida" in rechazada["motivo"].lower()
