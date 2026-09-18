"""Storage de archivos de evidencia (8.4): contrato propio, sin S3 en código de negocio.

Tres cosas distintas que nunca se mezclan:
  - Documento (fila en modulo1.documento) — el dato de negocio.
  - Archivo físico — identificado por `clave_storage`, estable, persistida en documento.
  - URL firmada — efímera, derivada al vuelo por `Storage`, NUNCA se persiste.

`obtener_storage()` es el único punto donde se elige la implementación (env
STORAGE_BACKEND, hoy solo `local`).
"""
from __future__ import annotations

from app.config import settings
from app.storage.contrato import Storage


def obtener_storage() -> Storage:
    backend = settings.storage_backend
    if backend == "local":
        from app.storage.local import StorageLocal

        return StorageLocal()
    raise ValueError(f"STORAGE_BACKEND desconocido: {backend}")
