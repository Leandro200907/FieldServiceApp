"""Lector XLSX endurecido para planilla standalone de OC (habilitante 1.12)."""
from __future__ import annotations

from typing import Any

from app.modules.operadoras.lector_xlsx import leer_planilla

ENCABEZADOS_UUID = (
    "clave_origen",
    "referencia",
    "cliente_id",
    "locacion_id",
    "tipo_servicio_id",
    "vigencia_desde",
    "vigencia_hasta",
    "estado",
)

ENCABEZADOS_NOMBRE = (
    "clave_origen",
    "referencia",
    "operadora",
    "locacion",
    "tipo_servicio",
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
    tiene_loc = "locacion" in header or "locación" in header
    tiene_tipo = "tipo_servicio" in header or "tipo de servicio" in header
    modo_nombre = "operadora" in header and tiene_loc and tiene_tipo
    modo_uuid = all(c in header for c in ("cliente_id", "locacion_id", "tipo_servicio_id"))
    if not modo_nombre and not modo_uuid:
        return [], ["columnas obligatorias: Operadora/Locación/Tipo de servicio o cliente_id/locacion_id/tipo_servicio_id"]
    columnas = ENCABEZADOS_NOMBRE if modo_nombre else ENCABEZADOS_UUID
    if modo_nombre:
        idx = {
            "clave_origen": header.index("clave_origen"),
            "referencia": header.index("referencia") if "referencia" in header else -1,
            "operadora": header.index("operadora"),
            "locacion": header.index("locación") if "locación" in header else header.index("locacion"),
            "tipo_servicio": header.index("tipo de servicio") if "tipo de servicio" in header else header.index("tipo_servicio"),
            "vigencia_desde": header.index("vigencia_desde"),
            "vigencia_hasta": header.index("vigencia_hasta"),
        }
        if "estado" in header:
            idx["estado"] = header.index("estado")
    else:
        idx = {name: header.index(name) for name in columnas if name in header}
    faltantes = [c for c in columnas if c not in idx and c not in ("estado", "referencia")]
    if faltantes:
        return [], [f"columnas obligatorias ausentes: {', '.join(faltantes)}"]
    salida: list[dict[str, Any]] = []
    for n, fila in enumerate(filas[1:], start=2):
        if not any(str(c).strip() for c in fila):
            continue
        item: dict[str, Any] = {}
        for col in columnas:
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
