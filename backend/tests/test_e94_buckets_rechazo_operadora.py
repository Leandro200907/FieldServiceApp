"""E-94: tarjetas de exigidos por calendario; rechazo operadora no es «vencido»."""
from __future__ import annotations

from datetime import date, timedelta

from app.modules.consultas.requisitos_exigidos_legajo import (
    AgregadoRequisitoExigido,
    resumen_exigidos_backlog,
)


def _ag(
    rid: str,
    *,
    sin_cobertura: bool = False,
    es_rechazo: bool = False,
    estado_peor: str = "vigente_todo_el_periodo",
    evidencia_id: str | None = "doc-1",
    vigente_hasta: date | None = None,
) -> AgregadoRequisitoExigido:
    ag = AgregadoRequisitoExigido(
        requisito_definicion_id=rid,
        nombre=rid,
        categoria="documento",
        tipo="documento",
        estado_peor=estado_peor,
        evidencia_id=evidencia_id,
        vigente_hasta=vigente_hasta,
        sin_cobertura=sin_cobertura,
        es_rechazo_operadora=es_rechazo,
        operadora_nombre="Vista" if es_rechazo else None,
    )
    return ag


def test_maria_cinco_exigidos_rechazo_operadora_no_suma_en_vencidos():
    """María demo: apto vigente rechazado por Vista → tarjeta Vigentes, no Vencidos."""
    hoy = date(2026, 10, 5)
    plazo = 30
    mapa = {
        "r1": _ag("r1", sin_cobertura=False),
        "r2": _ag("r2", sin_cobertura=False),
        "r3": _ag("r3", sin_cobertura=False),
        "r4": _ag("r4", sin_cobertura=False),
        "r5": _ag(
            "r5",
            sin_cobertura=True,
            es_rechazo=True,
            estado_peor="vigente_todo_el_periodo",
            vigente_hasta=hoy + timedelta(days=365),
        ),
    }
    res = resumen_exigidos_backlog(mapa, hoy, plazo)
    assert res["exigidos"] == 5
    assert res["en_regla_exigidos"] == 4
    assert res["observados_operadora"] == 1
    assert res["exigidos_vencidos"] == 0
    assert res["exigidos_por_vencer"] == 0
    assert res["exigidos_vigentes"] == 5
    assert res["exigidos_sin_documento"] == 0


def test_evidencia_invalida_sigue_en_tarjeta_vencidos():
    hoy = date(2026, 10, 5)
    mapa = {
        "r1": _ag("r1", sin_cobertura=True, estado_peor="evidencia_invalida"),
    }
    res = resumen_exigidos_backlog(mapa, hoy, 30)
    assert res["exigidos_vencidos"] == 1
