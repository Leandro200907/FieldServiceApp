"""Resolución de qué versión de documento cuenta para evaluar habilitación (D16, D19).

Un documento sin confirmar nunca habilita. Si hay propuesta vigente declarada y una versión
confirmada sucedida enlazada por `sucede_a`, la evaluación usa la confirmada. Si solo existe
la propuesta, el requisito queda en pendiente de revisión / requiere revisión.

D19: además debe estar verificado y tener respaldo válido (archivo del documento o, en
competencia/inducción, al menos un documento soporte con archivo válido).

Precedencia del estado documental agregado (motor, radar, acciones, paquete): en
`estado_documental.evaluar_requisito_documental`, las alertas por vencimiento/calendario
prevalecen sobre *pendiente de revisión* por respaldo; sin respaldo en un documento aún
vigente en el período sigue siendo revisión. Ver D19 en DECISIONES_DOMINIO.md.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


def es_propuesta_pendiente(fila: dict[str, Any]) -> bool:
    return bool(fila.get("origen_propuesta")) and fila.get("estado_confirmacion") == "declarado"


def _id_documento(fila: dict[str, Any]) -> str:
    return str(fila.get("documento_id") or fila.get("evidencia_id") or fila.get("id"))


def archivo_validacion_de_fila(fila: Mapping[str, Any]) -> str:
    """`sin_archivo` | `pendiente` | `valido` | `invalido` para una fila de modulo1.documento."""
    archivo_estado = fila.get("archivo_estado")
    if archivo_estado in ("sin_archivo", "purgado"):
        return "sin_archivo"
    clave = fila.get("clave_storage")
    if archivo_estado == "confirmado":
        if fila.get("archivo_validacion") is not None:
            return str(fila["archivo_validacion"])
        return "pendiente"
    if clave is None:
        return "sin_archivo"
    return "pendiente"


def _categoria_respaldo(categoria: str | None) -> str:
    return (categoria or "documento").lower()


def respaldo_valido(
    fila: Mapping[str, Any],
    *,
    categoria: str | None,
    soportes: Iterable[Mapping[str, Any]] | None = None,
) -> bool:
    cat = _categoria_respaldo(categoria)
    if cat in ("competencia", "induccion"):
        for soporte in soportes or ():
            if archivo_validacion_de_fila(soporte) == "valido":
                return True
        return False
    return archivo_validacion_de_fila(fila) == "valido"


def archivo_requiere_revision(
    fila: Mapping[str, Any],
    *,
    categoria: str | None,
    soportes: Iterable[Mapping[str, Any]] | None = None,
) -> bool:
    """True si el dato está verificado pero no alcanza respaldo válido para habilitar (D19)."""
    if fila.get("estado_confirmacion") != "verificado":
        return False
    if es_propuesta_pendiente(dict(fila)):
        return True
    return not respaldo_valido(fila, categoria=categoria, soportes=soportes)


def archivo_validacion_para_evaluacion_documental(
    fila: Mapping[str, Any],
    *,
    categoria: str | None,
    soportes: Iterable[Mapping[str, Any]] | None = None,
) -> str:
    """Archivo efectivo para radar / estado documental (misma regla de respaldo que D19)."""
    cat = _categoria_respaldo(categoria)
    if cat in ("competencia", "induccion"):
        validos = [s for s in (soportes or ()) if archivo_validacion_de_fila(s) == "valido"]
        if validos:
            return "valido"
        soportes_list = list(soportes or ())
        if not soportes_list:
            return "sin_archivo"
        peor = archivo_validacion_de_fila(soportes_list[0])
        for s in soportes_list[1:]:
            v = archivo_validacion_de_fila(s)
            if v == "invalido":
                peor = "invalido"
            elif v == "pendiente" and peor != "invalido":
                peor = "pendiente"
            elif v == "sin_archivo" and peor not in ("invalido", "pendiente"):
                peor = "sin_archivo"
        return peor
    return archivo_validacion_de_fila(fila)


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


def agrupar_soportes_por_documento(
    filas: Iterable[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """documento_padre_id (acreditación/inducción) → filas de documentos soporte."""
    salida: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in filas:
        d = dict(f)
        padre = str(d.pop("documento_padre_id", "") or d.pop("documento_id", "") or "")
        if padre:
            salida[padre].append(d)
    return salida
