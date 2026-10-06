"""Resolución de qué versión de documento cuenta para evaluar habilitación (D16, D19).

E-20: la propuesta vive en `estado_version = 'propuesta'`; el vigente confirmado no se sucede
hasta que el responsable aprueba. Para habilitación y vistas públicas se usa la fila `vigente`;
si solo hay propuesta pendiente, no hay cobertura confirmada (pendiente de revisión).

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
    return (
        fila.get("estado_version") == "propuesta"
        and fila.get("estado_confirmacion") == "declarado"
    )


def _id_documento(fila: dict[str, Any]) -> str:
    return str(fila.get("documento_id") or fila.get("evidencia_id") or fila.get("id"))


def archivo_validacion_de_fila(fila: Mapping[str, Any]) -> str:
    """`sin_archivo` | `pendiente` | `valido` | `invalido` para una fila de modulo1.documento.

    Fuente única (regla 15): presentación, ficha y dominio importan desde acá.
    `purgado` y ausencia de clave sin confirmación → `sin_archivo`; confirmado sin columna
    aún → `pendiente`.
    """
    archivo_estado = fila.get("archivo_estado")
    clave = fila.get("clave_storage")
    if archivo_estado in ("sin_archivo", "purgado"):
        return "sin_archivo"
    if archivo_estado == "sin_archivo" or (clave is None and archivo_estado != "confirmado"):
        return "sin_archivo"
    if archivo_estado == "confirmado":
        if fila.get("archivo_validacion") is not None:
            return str(fila["archivo_validacion"])
        return "pendiente"
    if clave is None:
        return "sin_archivo"
    return "pendiente"


def _categoria_respaldo(categoria: str | None) -> str:
    return (categoria or "documento").lower()


def _soporte_certificado_propio(soporte: Mapping[str, Any]) -> bool:
    return bool(soporte.get("es_certificado_propio"))


def respaldo_valido(
    fila: Mapping[str, Any],
    *,
    categoria: str | None,
    soportes: Iterable[Mapping[str, Any]] | None = None,
) -> bool:
    cat = _categoria_respaldo(categoria)
    if cat in ("competencia", "induccion"):
        for soporte in soportes or ():
            if not _soporte_certificado_propio(soporte):
                continue
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
    if es_propuesta_pendiente(dict(fila)):
        return True
    if fila.get("estado_confirmacion") != "verificado":
        return False
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
        certificados = [s for s in (soportes or ()) if _soporte_certificado_propio(s)]
        validos = [s for s in certificados if archivo_validacion_de_fila(s) == "valido"]
        if validos:
            return "valido"
        if not certificados:
            return "sin_archivo"
        soportes_list = certificados
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
    if vigente is not None:
        return vigente
    propuesta = next((g for g in grupo if g.get("estado_version") == "propuesta"), None)
    if propuesta is not None:
        return propuesta
    return None


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
