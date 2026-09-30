"""Lector XLSX endurecido para planilla standalone de OC (habilitante 1.12)."""
from __future__ import annotations

from typing import Any

from app.modules.operadoras.lector_xlsx import leer_planilla

ENCABEZADOS = (
    "clave_origen",
    "referencia",
    "cliente_id",
    "locacion_id",
    "tipo_servicio_id",
    "vigencia_desde",
    "vigencia_hasta",
    "estado",
)


def leer_planilla_oc(contenido: bytes, *, hoja: str = "OC") -> tuple[list[dict[str, Any]], list[str]]:
    filas, errores = leer_planilla(contenido, hoja=hoja)
    if errores:
        return [], errores
    if not filas:
        return [], ["planilla vacía"]
    header = [str(c).strip().lower() for c in filas[0]]
    idx = {name: header.index(name) for name in ENCABEZADOS if name in header}
    faltantes = [c for c in ENCABEZADOS if c not in idx and c != "estado"]
    if faltantes:
        return [], [f"columnas obligatorias ausentes: {', '.join(faltantes)}"]
    salida: list[dict[str, Any]] = []
    for n, fila in enumerate(filas[1:], start=2):
        if not any(str(c).strip() for c in fila):
            continue
        item: dict[str, Any] = {}
        for col in ENCABEZADOS:
            if col not in idx:
                continue
            val = fila[idx[col]]
            item[col] = str(val).strip() if val is not None and str(val).strip() else None
        if not item.get("clave_origen"):
            errores.append(f"fila {n}: clave_origen obligatoria")
            continue
        if item.get("estado") and item["estado"].lower() == "cancelado":
            item["estado"] = "cancelado"
        salida.append(item)
    return salida, errores
