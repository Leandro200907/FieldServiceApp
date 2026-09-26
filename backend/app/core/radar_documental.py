"""Agregación pura de resultados documentales, sin semántica operativa."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from app.core.estado_documental import EstadoRequisitoDocumental, ResultadoRequisitoDocumental


ESTADOS_ALERTA = frozenset({
    EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO,
    EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO,
    EstadoRequisitoDocumental.FALTANTE,
    EstadoRequisitoDocumental.EVIDENCIA_INVALIDA,
})
ESTADOS_INCOMPLETOS = frozenset({
    EstadoRequisitoDocumental.PENDIENTE_REVISION,
    EstadoRequisitoDocumental.NO_EVALUABLE,
})


@dataclass(frozen=True)
class ResumenDocumental:
    estado: str
    primer_quiebre: date | None
    con_alertas: int
    incompletos: int


def resumir_resultados(resultados: Iterable[ResultadoRequisitoDocumental]) -> ResumenDocumental:
    """Resume requisitos sin convertir cantidades en capacidad o cobertura."""
    resultados = tuple(resultados)
    alertas = tuple(r for r in resultados if r.estado in ESTADOS_ALERTA)
    incompletos = tuple(r for r in resultados if r.estado in ESTADOS_INCOMPLETOS)
    quiebres = [r.primer_quiebre for r in alertas if r.primer_quiebre is not None]
    if alertas:
        estado = "con_alertas_documentales"
    elif incompletos:
        estado = "informacion_incompleta"
    else:
        estado = "sin_alertas_documentales"
    return ResumenDocumental(
        estado=estado,
        primer_quiebre=min(quiebres) if quiebres else None,
        con_alertas=len(alertas),
        incompletos=len(incompletos),
    )


def resumir_oc(resumenes_legajo: Iterable[ResumenDocumental], *, sin_matriz: bool = False) -> ResumenDocumental:
    """Aplica la precedencia cerrada del contrato funcional del radar."""
    resumenes = tuple(resumenes_legajo)
    if sin_matriz:
        return ResumenDocumental("sin_matriz", None, 0, 0)
    alertas = sum(r.estado == "con_alertas_documentales" for r in resumenes)
    incompletos = sum(r.estado == "informacion_incompleta" for r in resumenes)
    quiebres = [r.primer_quiebre for r in resumenes if r.primer_quiebre is not None]
    if alertas:
        estado = "con_alertas_documentales"
    elif incompletos:
        estado = "informacion_incompleta"
    else:
        estado = "sin_alertas_documentales"
    return ResumenDocumental(estado, min(quiebres) if quiebres else None, alertas, incompletos)

