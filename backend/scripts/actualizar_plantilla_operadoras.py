"""Actualiza la plantilla pública de presentaciones de operadoras (columna Documento ID + Instrucciones)."""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

RAIZ = Path(__file__).resolve().parents[2]
DESTINOS = [
    RAIZ / "frontend" / "public" / "Plantilla_presentaciones_operadoras.xlsx",
]

ENCABEZADOS = [
    "Operadora", "Tipo de sujeto", "Identificador del sujeto", "Sujeto ID",
    "Tipo de documento", "Requisito ID", "Documento ID", "Fecha de emisión", "Fecha de vencimiento",
    "Estado", "Fecha de exportación", "Fecha de presentación", "Fecha de respuesta", "Observación",
]

INSTRUCCIONES = [
    "Complete la hoja Presentaciones. Cada fila actualiza el espejo de una operadora; no crea documentos del legajo.",
    "La operadora debe existir previamente en Catálogos OC (no se crean operadoras nuevas desde la planilla).",
    "Documento ID es opcional: use el UUID de la versión documental cuando haya ambigüedad.",
    "Fechas: celda de fecha Excel, ISO (aaaa-mm-dd) o texto dd/mm/aaaa.",
    "Estados válidos: exportado, enviado, aceptado, rechazado (con sus fechas asociadas).",
]


def actualizar(ruta: Path) -> None:
    wb = load_workbook(ruta)
    if "Presentaciones" not in wb.sheetnames:
        raise SystemExit(f"Falta hoja Presentaciones en {ruta}")
    hoja = wb["Presentaciones"]
    for col, titulo in enumerate(ENCABEZADOS, start=1):
        hoja.cell(row=5, column=col, value=titulo)
    if "Instrucciones" not in wb.sheetnames:
        hoja_inst = wb.create_sheet("Instrucciones")
    else:
        hoja_inst = wb["Instrucciones"]
    hoja_inst.delete_rows(1, hoja_inst.max_row or 1)
    for i, linea in enumerate(INSTRUCCIONES, start=1):
        hoja_inst.cell(row=i, column=1, value=linea)
    wb.save(ruta)


def main() -> int:
    for destino in DESTINOS:
        if not destino.is_file():
            raise SystemExit(f"No existe {destino}")
        actualizar(destino)
        print(f"Actualizado {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
