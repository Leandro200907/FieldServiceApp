"""Resumen de cobertura en vivo para consultas Módulo 1 (D-A bis, habilitante 1.12)."""
from __future__ import annotations

from typing import Any

from app.core.tipos import ResultadoDecision, Veredicto

_ETIQUETA_TIPO = {"persona": "persona", "vehiculo": "vehículo", "equipo": "equipo", "empresa": "empresa"}


def motivo_requisito_faltante_112(nombre: str, tipo_sujeto: str) -> str:
    etiqueta = _ETIQUETA_TIPO.get(tipo_sujeto, tipo_sujeto)
    return f"requisito_faltante: {nombre} — ningún legajo de tipo {etiqueta} lo posee"


def estado_cobertura_global(
    evaluacion: dict[str, Any],
    *,
    sin_matriz: bool = False,
) -> str:
    if sin_matriz:
        return "sin_matriz"
    por_sujeto = evaluacion.get("por_sujeto") or []
    empresa = next((s for s in por_sujeto if s.get("tipo_sujeto") == "empresa" and s.get("representante")), None)
    snap = evaluacion.get("snapshot") or {}
    if snap.get("empresa_sin_evaluar") or (empresa is not None and not empresa.get("asignable")):
        return "empresa_bloquea"
    if evaluacion.get("resultado_de_decision") != ResultadoDecision.NO_PUEDE_ASIGNARSE.value:
        return "cubierta"
    return "no_cubierta"


def _tipos_recurso_exigidos(evaluacion: dict[str, Any]) -> list[str]:
    snap = evaluacion.get("snapshot") or {}
    tipos = snap.get("tipos_exigidos") or {}
    if isinstance(tipos, dict):
        return [t for t in tipos if t != "empresa"]
    return [t for t in tipos if t != "empresa"]


def resumen_por_tipo(evaluacion: dict[str, Any]) -> list[dict[str, Any]]:
    """Por cada tipo de recurso exigido: conteo de candidatos asignables y motivo 1.12."""
    tipos_fuera = set(evaluacion.get("tipos_fuera_de_alcance") or [])
    por_sujeto = evaluacion.get("por_sujeto") or []
    faltantes = evaluacion.get("requisitos_faltantes") or []
    salida: list[dict[str, Any]] = []
    for tipo in _tipos_recurso_exigidos(evaluacion):
        if tipo in tipos_fuera:
            salida.append({
                "tipo_sujeto": tipo,
                "estado": "fuera_de_alcance",
                "candidatos_cumplen": 0,
                "motivo": "Hay recursos de este tipo fuera de tu alcance",
            })
            continue
        cumplen = sum(
            1 for s in por_sujeto
            if s.get("tipo_sujeto") == tipo and s.get("asignable")
        )
        motivo = None
        if cumplen == 0:
            rf = next(
                (f for f in faltantes if f.get("tipo_sujeto") == tipo and f.get("requisito_definicion_id")),
                None,
            )
            if rf and rf.get("nombre"):
                motivo = motivo_requisito_faltante_112(rf["nombre"], tipo)
            else:
                rf2 = next((f for f in faltantes if f.get("tipo_sujeto") == tipo), None)
                if rf2 and rf2.get("nombre"):
                    motivo = motivo_requisito_faltante_112(rf2["nombre"], tipo)
                elif rf2 and rf2.get("motivo"):
                    motivo = rf2["motivo"]
        salida.append({
            "tipo_sujeto": tipo,
            "estado": "cubierta" if cumplen > 0 else "no_cubierta",
            "candidatos_cumplen": cumplen,
            "motivo": motivo,
        })
    return salida


def candidatos_detalle(evaluacion: dict[str, Any]) -> list[dict[str, Any]]:
    """Agrupa evaluados por tipo con requisitos y primer quiebre inferido del veredicto."""
    por_tipo: dict[str, list[dict[str, Any]]] = {}
    for sujeto in evaluacion.get("por_sujeto") or []:
        if sujeto.get("tipo_sujeto") == "empresa":
            continue
        tipo = sujeto["tipo_sujeto"]
        requisitos = []
        primer_quiebre = None
        for req in sujeto.get("requisitos") or []:
            v = req.get("veredicto")
            pq = None
            if v == Veredicto.VENCE_DURANTE_EL_TRABAJO.value:
                pq = (evaluacion.get("snapshot") or {}).get("oc", {}).get("vigencia_hasta")
            requisitos.append({
                "requisito_definicion_id": req.get("requisito_definicion_id"),
                "nombre": req.get("nombre"),
                "veredicto": v,
                "motivo": req.get("motivo"),
                "asignable": req.get("asignable"),
                "primer_quiebre": pq,
            })
            if pq and (primer_quiebre is None or str(pq) < str(primer_quiebre)):
                primer_quiebre = pq
        por_tipo.setdefault(tipo, []).append({
            "sujeto_id": sujeto["sujeto_id"],
            "tipo_sujeto": tipo,
            "asignable": sujeto.get("asignable"),
            "veredicto": sujeto.get("veredicto"),
            "primer_quiebre": primer_quiebre,
            "requisitos": requisitos,
        })
    return [{"tipo_sujeto": t, "candidatos": c} for t, c in sorted(por_tipo.items())]
