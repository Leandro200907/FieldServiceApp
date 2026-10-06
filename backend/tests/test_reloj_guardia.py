"""E-106: el dominio no debe leer el reloj del SO fuera de app/comun/reloj.py."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[1] / "app"
_RELOJ = _APP / "comun" / "reloj.py"

_PATRONES = (
    re.compile(r"\bdatetime\.now\s*\("),
    re.compile(r"\bdatetime\.utcnow\s*\("),
    re.compile(r"\bdate\.today\s*\("),
)


def _archivos_app() -> list[Path]:
    return [p for p in _APP.rglob("*.py") if p.resolve() != _RELOJ.resolve()]


def _lineas_sospechosas(path: Path) -> list[str]:
    texto = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(texto, filename=str(path))
    except SyntaxError:
        return [f"{path}: no se pudo parsear"]
    hallazgos: list[str] = []
    for nodo in ast.walk(tree):
        if not isinstance(nodo, ast.Call):
            continue
        fuente = ast.get_source_segment(texto, nodo) or ""
        if not any(p.search(fuente) for p in _PATRONES):
            continue
        hallazgos.append(f"{path.relative_to(_APP.parent)}:{nodo.lineno}: {fuente.strip()}")
    return hallazgos


def test_app_no_usa_reloj_del_sistema_fuera_de_reloj_py():
    violaciones: list[str] = []
    for path in _archivos_app():
        violaciones.extend(_lineas_sospechosas(path))
    assert violaciones == [], "Usar app.comun.reloj.ahora_utc / hoy_del_tenant:\n" + "\n".join(violaciones)


def test_reloj_congelado_fijo_independiente_de_fecha_pared():
    """FSM_TEST_SIMULAR_FECHA_PARED documenta el calendario real; el autouse no lo usa."""
    import os

    if not os.environ.get("FSM_TEST_SIMULAR_FECHA_PARED"):
        pytest.skip("Definí FSM_TEST_SIMULAR_FECHA_PARED (p. ej. 2027-06-01) en la 2.ª corrida de suite")

    from app.comun.reloj import ahora_utc

    from tests.conftest import AHORA_PYTEST_DEFAULT

    assert ahora_utc() == AHORA_PYTEST_DEFAULT


def test_reloj_congelado_resiste_fecha_simulada_por_env(reloj_congelado_en_tests):
    from app.comun.reloj import ahora_utc

    assert ahora_utc() == reloj_congelado_en_tests
