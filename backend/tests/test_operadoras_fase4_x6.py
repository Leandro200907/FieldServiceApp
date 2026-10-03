"""Fase 4 X-6: tope de 1000 filas durante el parseo streaming."""
from __future__ import annotations

import pytest

from app.api.errores import ErrorDeDominio
from tests.test_lector_xlsx_seguridad import _ENC, _fila_datos, _fila_inline, _xlsx_minimo


def test_iterparse_corta_en_mil_filas_de_datos():
    enc = _fila_inline(5, _ENC)
    filas = enc + "".join(_fila_datos(6 + i, f"id{i}") for i in range(1001))
    xlsx = _xlsx_minimo(filas)
    with pytest.raises(ErrorDeDominio, match="1000 filas"):
        from app.modules.operadoras.lector_xlsx import leer_planilla

        leer_planilla(xlsx)
