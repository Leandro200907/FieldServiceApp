"""E-10: rechazo de operadora bloquea solo en OCs de esa operadora."""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.consulta_documental import ajustar_por_espejo_operadora
from app.core.estado_documental import (
    EstadoRequisitoDocumental,
    ResultadoRequisitoDocumental,
)


def test_ajustar_rechazo_operadora_bloquea_con_motivo():
    base = ResultadoRequisitoDocumental(
        estado=EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO,
        primer_quiebre=None,
        evidencia_id="doc-1",
        motivo="ok",
        accion_sugerida=None,
    )
    entregas = {
        ("op-vista", "doc-1"): {
            "estado": "rechazado",
            "rechazado_en": datetime(2026, 9, 15, tzinfo=timezone.utc),
            "operadora_nombre": "Vista",
        }
    }
    nuevo, aviso, accion = ajustar_por_espejo_operadora(
        base,
        operadora_id="op-vista",
        operadora_nombre="Vista",
        entregas=entregas,
    )
    assert aviso == "rechazado"
    assert "Rechazado por Vista el 15/09/2026" in nuevo.motivo

    sin_fecha, _, _ = ajustar_por_espejo_operadora(
        base,
        operadora_id="op-vista",
        operadora_nombre="Vista",
        entregas={
            ("op-vista", "doc-1"): {
                "estado": "rechazado",
                "rechazado_en": None,
                "operadora_nombre": "Vista",
            }
        },
    )
    assert "fecha no informada" in sin_fecha.motivo
    assert accion == "Regularizar ante Vista"
    assert nuevo.estado == EstadoRequisitoDocumental.FALTANTE

    aceptado, aviso2, _ = ajustar_por_espejo_operadora(
        base,
        operadora_id="op-ypf",
        operadora_nombre="YPF",
        entregas={("op-ypf", "doc-1"): {"estado": "aceptado", "operadora_nombre": "YPF"}},
    )
    assert aviso2 is None
    assert aceptado.estado == EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO
