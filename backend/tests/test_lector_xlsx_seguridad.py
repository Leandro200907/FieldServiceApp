"""Límites del lector XLSX de operadoras (sin Postgres)."""
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.api.errores import ErrorDeDominio
from app.modules.operadoras.lector_xlsx import leer_planilla


def test_rechaza_parte_descomprimida_excesiva_en_metadatos_zip():
    contenido = BytesIO()
    with ZipFile(contenido, "w", ZIP_DEFLATED) as z:
        info = ZipInfo("xl/sharedStrings.xml")
        info.file_size = 3 * 1024 * 1024
        z.writestr(info, b"x")
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook/>')
    with pytest.raises(ErrorDeDominio, match="demasiado grande"):
        leer_planilla(contenido.getvalue())
