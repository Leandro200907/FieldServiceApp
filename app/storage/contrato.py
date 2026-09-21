"""Contrato de storage — lo único que conoce el código de negocio y el worker.

Las implementaciones (local, y en el futuro un bucket) cumplen este Protocol. Las URL
que devuelve son efímeras: se derivan al vuelo y no se guardan en ningún lado.

Regla de claves (A-02 de la auditoría): la clave la deriva SIEMPRE el servidor con
`clave_para(tenant_id, documento_id, nombre)` = `tenant_id/documento_id/nombre`. El
tenant y el documento quedan embebidos en la clave y la base los verifica
(`ck_archivo_clave_del_documento`); ningún body público puede elegirla.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class InfoArchivo:
    bytes: int
    checksum_sha256: str


class Storage(Protocol):
    def clave_para(self, tenant_id: str, documento_id: str, nombre_archivo: str) -> str:
        """Clave estable del archivo físico: `tenant_id/documento_id/nombre_saneado`."""
        ...

    def url_prefirmada_put(self, clave: str, content_type: str, expira_seg: int, max_bytes: int) -> str:
        """URL para que el cliente suba el archivo directo al storage (PUT). Content-Type y
        tamaño máximo viajan firmados y el storage los exige al recibir."""
        ...

    def url_prefirmada_get(self, clave: str, expira_seg: int) -> str:
        """URL efímera de descarga."""
        ...

    def existe(self, clave: str) -> bool: ...

    def inspeccionar(self, clave: str) -> InfoArchivo | None:
        """Tamaño y checksum calculados desde el archivo REAL (nunca declarados por el
        cliente). None si no existe."""
        ...

    def leer(self, clave: str) -> bytes:
        """Bytes reales, sólo para lectura server-side de confianza (validación técnica
        de evidencia, Fase 2 punto 2) — nunca se expone al cliente; para eso están las
        URLs prefirmadas. `FileNotFoundError` si no existe."""
        ...

    def borrar(self, clave: str) -> bool:
        """True SOLO si el borrado físico se confirmó (o el archivo ya no existía). Si
        devuelve False el llamador no debe dar el archivo por purgado."""
        ...

    def disponible(self) -> bool:
        """Readiness: el backend puede leer y escribir ahora mismo. Nunca lanza."""
        ...
