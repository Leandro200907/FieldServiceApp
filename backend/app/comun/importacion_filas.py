"""Utilidades compartidas para mensajes y orden de errores de importación por fila."""
from __future__ import annotations

from typing import Any


def ordenar_por_fila(errores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(errores, key=lambda e: (e.get("fila") is None, e.get("fila") if isinstance(e.get("fila"), int) else 0))


def mensaje_fecha_invalida(fila: int, etiqueta_columna: str, valor: object) -> str:
    mostrado = "" if valor is None else str(valor).strip()
    return f"Fila {fila}, {etiqueta_columna}: '{mostrado}' no es una fecha válida (formato dd/mm/aaaa)"
