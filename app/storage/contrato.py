"""Contrato de storage — lo único que conoce el código de negocio y el worker.

Las implementaciones (local, y en el futuro un bucket) cumplen este Protocol. Las URL
que devuelve son efímeras: se derivan al vuelo y no se guardan en ningún lado.
"""
from __future__ import annotations

from typing import Protocol


class Storage(Protocol):
    def clave_para(self, tenant_id: str, documento_id: str, nombre_archivo: str) -> str:
        """Clave estable del archivo físico, con prefijo por tenant."""
        ...

    def url_prefirmada_put(self, clave: str, content_type: str, expira_seg: int) -> str:
        """URL para que el cliente suba el archivo directo al storage (PUT)."""
        ...

    def url_prefirmada_get(self, clave: str, expira_seg: int) -> str:
        """URL efímera de descarga."""
        ...

    def existe(self, clave: str) -> bool: ...

    def borrar(self, clave: str) -> bool:
        """True SOLO si el borrado físico se confirmó. Si devuelve False el llamador no
        debe dar el archivo por purgado."""
        ...
