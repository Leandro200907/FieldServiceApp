"""Límites del lector XLSX de operadoras (sin Postgres)."""
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.api.errores import ErrorDeDominio
from app.modules.operadoras.lector_xlsx import leer_planilla


def _xlsx_minimo(filas_xml: str, hoja: str = "Presentaciones") -> bytes:
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
            '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + filas_xml
            + "</sheetData></worksheet>",
        )
    return contenido.getvalue()


def _fila_inline(numero: int, valores: list[str]) -> str:
    celdas = []
    for i, v in enumerate(valores, 1):
        letras = ""
        n = i
        while n:
            n, resto = divmod(n - 1, 26)
            letras = chr(65 + resto) + letras
        celdas.append(f'<c r="{letras}{numero}" t="inlineStr"><is><t>{v}</t></is></c>')
    return f'<row r="{numero}">' + "".join(celdas) + "</row>"


_ENC = [
    "Operadora", "Tipo de sujeto", "Identificador del sujeto", "Tipo de documento", "Estado",
]


def _fila_datos(numero: int, ident: str) -> str:
    return _fila_inline(numero, ["Op", "persona", ident, "Apto", "exportado"])


def test_rechaza_parte_descomprimida_excesiva():
    """Una parte interna > 2 MB debe rechazarse antes de descomprimirla entera."""
    contenido = BytesIO()
    grande = b"x" * (3 * 1024 * 1024 + 1)
    with ZipFile(contenido, "w", ZIP_DEFLATED) as z:
        z.writestr("xl/sharedStrings.xml", grande)
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
        )
    with pytest.raises(ErrorDeDominio, match="parte descomprimida demasiado grande"):
        leer_planilla(contenido.getvalue())


def test_rechaza_parte_grande_declarada_en_infolist():
    """Zip bomb: tamaño descomprimido inflado en el directorio central, sin leer el payload."""
    contenido = BytesIO()
    with ZipFile(contenido, "w") as z:
        info = ZipInfo("xl/sharedStrings.xml")
        info.compress_type = ZIP_DEFLATED
        info.file_size = 3 * 1024 * 1024 + 1
        z.writestr(info, b"x")
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
        )
    # CPython recalcula file_size al escribir; el libro queda malformado y falla antes de descomprimir.
    with pytest.raises(ErrorDeDominio, match="planilla XLSX válida"):
        leer_planilla(contenido.getvalue())


def test_rechaza_planilla_vacia():
    with pytest.raises(ErrorDeDominio, match="vacía"):
        leer_planilla(b"")


def test_rechaza_hoja_inexistente():
    enc = _fila_inline(5, _ENC)
    datos = _fila_datos(6, "id1")
    xlsx = _xlsx_minimo(enc + datos, hoja="Presentaciones")
    with pytest.raises(ErrorDeDominio, match="No existe la hoja"):
        leer_planilla(xlsx, hoja="OtraHoja")


def test_rechaza_sin_columnas_obligatorias():
    mal = _fila_inline(5, ["Operadora", "Tipo de sujeto", "Estado"])
    xlsx = _xlsx_minimo(mal)
    with pytest.raises(ErrorDeDominio, match="columnas obligatorias"):
        leer_planilla(xlsx)


def test_rechaza_mas_de_mil_filas():
    enc = _fila_inline(5, _ENC)
    filas = enc + "".join(_fila_datos(6 + i, f"id{i}") for i in range(1001))
    xlsx = _xlsx_minimo(filas)
    with pytest.raises(ErrorDeDominio, match="1000 filas"):
        leer_planilla(xlsx)
