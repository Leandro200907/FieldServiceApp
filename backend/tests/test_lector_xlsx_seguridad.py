"""Límites del lector XLSX de operadoras (sin Postgres)."""
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.api.errores import ErrorDeDominio
from app.modules.operadoras.lector_xlsx import leer_planilla


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
    with pytest.raises(ErrorDeDominio, match="demasiado grande"):
        leer_planilla(contenido.getvalue())
