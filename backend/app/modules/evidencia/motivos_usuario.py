"""Textos de validación técnica entendibles para técnicos (Flujo C)."""
from __future__ import annotations

_MENSAJE_ARCHIVO_INVALIDO = (
    "El archivo está dañado o no es una imagen/PDF válido. Volvé a sacar la foto o subí un PDF legible."
)


def motivo_validacion_para_usuario(motivo_tecnico: str | None) -> str:
    if not motivo_tecnico:
        return _MENSAJE_ARCHIVO_INVALIDO
    m = motivo_tecnico.lower()
    if "formato reconocible" in m or "pdf corrupto" in m or "no coincide con el tipo" in m:
        return _MENSAJE_ARCHIVO_INVALIDO
    if "checksum" in m:
        return "El archivo se corrompió al subirlo. Volvé a adjuntarlo."
    if motivo_tecnico.startswith("validación técnica del archivo:"):
        return motivo_validacion_para_usuario(motivo_tecnico.split(":", 1)[1].strip())
    if motivo_tecnico.startswith("invalidado manualmente"):
        return motivo_tecnico
    return _MENSAJE_ARCHIVO_INVALIDO
