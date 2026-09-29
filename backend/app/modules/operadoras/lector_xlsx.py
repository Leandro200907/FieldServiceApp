"""Lector mínimo y seguro del formato XLSX usado por la planilla de operadoras.

No interpreta macros, fórmulas ni vínculos externos. Sólo extrae valores de celdas del
libro ZIP/XML estándar, suficiente para mantener la importación independiente de Excel.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
import re
import unicodedata
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET

from app.api.errores import ErrorDeDominio


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_COLUMNAS = {
    "operadora": "operadora",
    "tipo sujeto": "tipo_sujeto",
    "tipo de sujeto": "tipo_sujeto",
    "identificador sujeto": "identificador_sujeto",
    "identificador del sujeto": "identificador_sujeto",
    "sujeto id": "sujeto_id",
    "tipo documento": "tipo_documento",
    "tipo de documento": "tipo_documento",
    "requisito id": "requisito_id",
    "fecha emision": "fecha_emision",
    "fecha de emision": "fecha_emision",
    "fecha vencimiento": "fecha_vencimiento",
    "fecha de vencimiento": "fecha_vencimiento",
    "estado": "estado",
    "fecha exportacion": "fecha_exportacion",
    "fecha de exportacion": "fecha_exportacion",
    "fecha presentacion": "fecha_presentacion",
    "fecha de presentacion": "fecha_presentacion",
    "fecha respuesta": "fecha_respuesta",
    "fecha de respuesta": "fecha_respuesta",
    "observacion": "observacion",
}
_REQUERIDAS = {"operadora", "tipo_sujeto", "identificador_sujeto", "tipo_documento", "estado"}
_MAX_PARTE_DESCOMPRIMIDA = 2 * 1024 * 1024


def _leer_parte_zip(libro: ZipFile, nombre: str) -> bytes:
    info = libro.getinfo(nombre)
    if info.file_size > _MAX_PARTE_DESCOMPRIMIDA:
        raise ErrorDeDominio("La planilla contiene una parte descomprimida demasiado grande")
    return libro.read(nombre)


def _normalizar(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "").strip())
    return re.sub(r"\s+", " ", "".join(c for c in texto if not unicodedata.combining(c)).lower())


def _columna(referencia: str) -> int:
    letras = re.match(r"[A-Z]+", referencia)
    if not letras:
        return 0
    numero = 0
    for letra in letras.group(0):
        numero = numero * 26 + ord(letra) - 64
    return numero


def _texto_compartido(raiz: ET.Element) -> list[str]:
    return ["".join(n.text or "" for n in si.iter(f"{_NS}t")) for si in raiz.findall(f"{_NS}si")]


def _valor(celda: ET.Element, compartidos: list[str]) -> object:
    tipo = celda.attrib.get("t")
    if tipo == "inlineStr":
        return "".join(n.text or "" for n in celda.iter(f"{_NS}t"))
    nodo = celda.find(f"{_NS}v")
    if nodo is None or nodo.text is None:
        return None
    bruto = nodo.text
    if tipo == "s":
        return compartidos[int(bruto)]
    if tipo in {"str", "e"}:
        return bruto
    if tipo == "b":
        return bruto == "1"
    try:
        numero = float(bruto)
        return int(numero) if numero.is_integer() else numero
    except ValueError:
        return bruto


def _fecha(valor: object, *, con_hora: bool) -> date | datetime | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        resultado = datetime(1899, 12, 30) + timedelta(days=float(valor))
        return resultado if con_hora else resultado.date()
    texto = str(valor).strip().replace("Z", "+00:00")
    try:
        resultado = datetime.fromisoformat(texto)
        return resultado if con_hora else resultado.date()
    except ValueError:
        try:
            resultado_fecha = date.fromisoformat(texto)
            return datetime.combine(resultado_fecha, datetime.min.time()) if con_hora else resultado_fecha
        except ValueError as exc:
            raise ErrorDeDominio("Fecha inválida en la planilla", {"valor": str(valor)}) from exc


def leer_planilla(contenido: bytes, *, hoja: str = "Presentaciones") -> list[dict]:
    if not contenido:
        raise ErrorDeDominio("La planilla está vacía")
    if len(contenido) > 5 * 1024 * 1024:
        raise ErrorDeDominio("La planilla supera el máximo de 5 MB")
    try:
        with ZipFile(BytesIO(contenido)) as libro:
            nombres = libro.namelist()
            if any(info.file_size > _MAX_PARTE_DESCOMPRIMIDA for info in libro.infolist()):
                raise ErrorDeDominio("La planilla contiene una parte descomprimida demasiado grande")
            compartidos: list[str] = []
            if "xl/sharedStrings.xml" in nombres:
                compartidos = _texto_compartido(ET.fromstring(_leer_parte_zip(libro, "xl/sharedStrings.xml")))
            wb = ET.fromstring(_leer_parte_zip(libro, "xl/workbook.xml"))
            relaciones = ET.fromstring(_leer_parte_zip(libro, "xl/_rels/workbook.xml.rels"))
            destinos = {r.attrib["Id"]: r.attrib["Target"] for r in relaciones.findall(f"{_PKG_REL_NS}Relationship")}
            hojas = wb.find(f"{_NS}sheets")
            hoja_nodo = next((s for s in list(hojas) if s.attrib.get("name") == hoja), None) if hojas is not None else None
            if hoja_nodo is None:
                raise ErrorDeDominio("No existe la hoja requerida", {"hoja": hoja})
            destino = destinos[hoja_nodo.attrib[f"{_REL_NS}id"]].lstrip("/")
            ruta = destino if destino.startswith("xl/") else f"xl/{destino}"
            raiz = ET.fromstring(_leer_parte_zip(libro, ruta))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ErrorDeDominio("El archivo no es una planilla XLSX válida") from exc

    filas: list[tuple[int, dict[int, object]]] = []
    for fila in raiz.iter(f"{_NS}row"):
        numero = int(fila.attrib.get("r", "0"))
        valores = {_columna(c.attrib.get("r", "")): _valor(c, compartidos) for c in fila.findall(f"{_NS}c")}
        filas.append((numero, valores))

    encabezado: tuple[int, dict[int, str]] | None = None
    for numero, valores in filas[:20]:
        mapeo = {col: _COLUMNAS[n] for col, valor in valores.items() if (n := _normalizar(valor)) in _COLUMNAS}
        if _REQUERIDAS <= set(mapeo.values()):
            encabezado = numero, mapeo
            break
    if encabezado is None:
        raise ErrorDeDominio("No se encontraron las columnas obligatorias de la plantilla")

    fila_encabezado, columnas = encabezado
    resultado: list[dict] = []
    for numero, valores in filas:
        if numero <= fila_encabezado:
            continue
        registro = {nombre: valores.get(col) for col, nombre in columnas.items()}
        if not any(registro.get(c) not in (None, "") for c in _REQUERIDAS):
            continue
        registro["fila"] = numero
        for campo in ("fecha_emision", "fecha_vencimiento"):
            registro[campo] = _fecha(registro.get(campo), con_hora=False)
        for campo in ("fecha_exportacion", "fecha_presentacion", "fecha_respuesta"):
            registro[campo] = _fecha(registro.get(campo), con_hora=True)
        resultado.append(registro)
    if not resultado:
        raise ErrorDeDominio("La hoja no contiene filas para importar", {"hoja": hoja})
    if len(resultado) > 1000:
        raise ErrorDeDominio("La planilla supera el máximo de 1000 filas")
    return resultado

