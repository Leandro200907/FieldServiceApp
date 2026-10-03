"""Normalización de texto para resolución de catálogos (sin acentos, minúsculas)."""
from __future__ import annotations

import unicodedata


def normalizar_clave(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.replace("_", " ")).encode("ascii", "ignore").decode()
    base = base.replace(".", "")
    return " ".join(base.lower().split())
