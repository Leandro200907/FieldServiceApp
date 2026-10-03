"""Lector XLSX propio de la planilla standalone de OC.

Reutiliza sólo la lectura segura ZIP/XML (`leer_celdas_hoja`, fechas y normalización de
encabezados). No usa `leer_planilla` de operadoras: esa función exige otras columnas y
devuelve `list[dict]`, no `(filas, errores)`.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.api.errores import ErrorDeDominio
from app.comun.importacion_filas import mensaje_fecha_invalida
from app.modules.operadoras.lector_xlsx import _celda_con_contenido, _fecha, _normalizar, leer_celdas_hoja

_COLUMNAS = {
    "clave oc": "clave_origen",
    "clave_origen": "clave_origen",
    "referencia": "referencia",
    "operadora": "operadora",
    "locacion": "locacion",
    "tipo de servicio": "tipo_servicio",
    "tipo_servicio": "tipo_servicio",
    "vigencia desde": "vigencia_desde",
    "vigencia_desde": "vigencia_desde",
    "vigencia hasta": "vigencia_hasta",
    "vigencia_hasta": "vigencia_hasta",
    "estado": "estado",
    "cliente_id": "cliente_id",
    "locacion_id": "locacion_id",
    "tipo_servicio_id": "tipo_servicio_id",
}

_REQUERIDAS_NOMBRE = {"clave_origen", "operadora", "locacion", "tipo_servicio", "vigencia_desde", "vigencia_hasta"}
_REQUERIDAS_UUID = {"clave_origen", "cliente_id", "locacion_id", "tipo_servicio_id", "vigencia_desde", "vigencia_hasta"}
_FECHAS = ("vigencia_desde", "vigencia_hasta")
_ETIQUETAS_FECHA = {"vigencia_desde": "Vigencia desde", "vigencia_hasta": "Vigencia hasta"}


def _iso_fecha(valor: object) -> str:
    convertido = _fecha(valor, con_hora=False)
    if convertido is None:
        raise ErrorDeDominio("Fecha inválida en la planilla", {"valor": str(valor)})
    if isinstance(convertido, datetime):
        return convertido.date().isoformat()
    if isinstance(convertido, date):
        return convertido.isoformat()
    return str(convertido)


def leer_planilla_oc(contenido: bytes, *, hoja: str = "OC") -> tuple[list[dict[str, Any]], list[str]]:
    try:
        celdas = leer_celdas_hoja(contenido, hoja=hoja)
    except ErrorDeDominio as exc:
        return [], [exc.mensaje]

    encabezado: tuple[int, dict[int, str]] | None = None
    for numero, valores in celdas[:20]:
        mapeo = {col: _COLUMNAS[n] for col, valor in valores.items() if (n := _normalizar(valor)) in _COLUMNAS}
        nombres = set(mapeo.values())
        if _REQUERIDAS_NOMBRE <= nombres or _REQUERIDAS_UUID <= nombres:
            encabezado = numero, mapeo
            break
    if encabezado is None:
        return [], [
            "columnas obligatorias: Clave OC, Referencia, Operadora, Locación, Tipo de servicio, "
            "Vigencia desde, Vigencia hasta y Estado"
        ]

    fila_encabezado, columnas = encabezado
    salida: list[dict[str, Any]] = []
    errores: list[str] = []
    for numero, valores in celdas:
        if numero <= fila_encabezado:
            continue
        if not any(_celda_con_contenido(valores.get(col)) for col in columnas):
            continue
        registro = {nombre: valores.get(col) for col, nombre in columnas.items()}
        item: dict[str, Any] = {"fila": numero}
        for campo, val in registro.items():
            if val is None or str(val).strip() == "":
                item[campo] = None
                continue
            if campo in _FECHAS:
                try:
                    item[campo] = _iso_fecha(val)
                except ErrorDeDominio:
                    errores.append(mensaje_fecha_invalida(numero, _ETIQUETAS_FECHA[campo], val))
                    item = {}
                    break
            else:
                item[campo] = str(val).strip()
        if not item:
            continue
        if not item.get("clave_origen"):
            errores.append(f"Fila {numero}, Clave OC: falta el valor obligatorio")
            continue
        if not str(item.get("operadora") or "").strip():
            errores.append(f"Fila {numero}: Falta la operadora")
            continue
        if item.get("estado") and item["estado"].lower() == "cancelado":
            item["estado"] = "cancelado"
        salida.append(item)
    if not salida and not errores:
        return [], ["planilla vacía"]
    if len(salida) > 1000:
        return [], ["La planilla supera el máximo de 1000 filas"]
    return salida, errores
