"""Resolución de qué versión de documento cuenta para evaluar habilitación (D16).

Un documento sin confirmar nunca habilita. Si hay propuesta vigente declarada y una versión
confirmada sucedida enlazada por `sucede_a`, la evaluación usa la confirmada. Si solo existe
la propuesta, el requisito queda en pendiente de revisión / requiere revisión.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def es_propuesta_pendiente(fila: dict[str, Any]) -> bool:
    return bool(fila.get("origen_propuesta")) and fila.get("estado_confirmacion") == "declarado"


def _id_documento(fila: dict[str, Any]) -> str:
    return str(fila.get("documento_id") or fila.get("evidencia_id") or fila.get("id"))


def fila_para_evaluacion(grupo: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Fila única que representa la evidencia evaluable para un (sujeto, requisito)."""
    vigente = next((g for g in grupo if g.get("estado_version") == "vigente"), None)
    if vigente is None:
        # Sin versión vigente no hay evidencia activa; las sucedidas solas no habilitan (D16).
        return None

    if es_propuesta_pendiente(vigente) and vigente.get("sucede_a"):
        objetivo = str(vigente["sucede_a"])
        confirmada = next(
            (
                g
                for g in grupo
                if g.get("estado_version") == "sucedida" and _id_documento(g) == objetivo
            ),
            None,
        )
        if confirmada is not None:
            return {**confirmada, "estado_version": "vigente"}
        return vigente

    if es_propuesta_pendiente(vigente):
        return vigente

    return vigente


def agrupar_filas_documento(filas: Iterable[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    por_clave: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in filas:
        d = dict(f)
        por_clave[(str(d["sujeto_id"]), str(d["requisito_definicion_id"]))].append(d)
    return por_clave


def filas_evidencia_para_evaluacion(
    filas: Iterable[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Mapa (sujeto_id, requisito_definicion_id) → fila elegida para evaluación."""
    salida: dict[tuple[str, str], dict[str, Any]] = {}
    for clave, grupo in agrupar_filas_documento(filas).items():
        elegida = fila_para_evaluacion(grupo)
        if elegida is not None:
            salida[clave] = elegida
    return salida
