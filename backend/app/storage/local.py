"""Storage de desarrollo sobre filesystem con URLs firmadas HMAC.

La "URL prefirmada" local es `{base_url}/{firma}` donde `firma` es un token
`base64url(json) . hmac_sha256` que lleva clave, tenant, operación (put/get),
content_type (solo put) y vencimiento. `app/storage/router.py` la valida y sirve el
archivo. La firma nunca se persiste: se deriva cada vez.

Configuración: `settings.storage_local_dir`, `settings.storage_local_base_url` y el
secreto de firma `settings.storage_secret` — distinto del JWT a propósito (A-02): una
filtración de uno no compromete al otro.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.api.errores import Prohibido
from app.comun.reloj import ahora_utc
from app.config import settings
from app.storage.contrato import InfoArchivo

_NOMBRE_SEGURO = re.compile(r"[^A-Za-z0-9._-]+")
# tenant_id / documento_id / nombre — sin puntos sueltos en los segmentos de id, así no
# hay forma de escribir ".." ni separadores raros (defensa en profundidad además del
# chequeo de traversal en `ruta`).
_CLAVE_VALIDA = re.compile(r"^[0-9a-fA-F-]{36}/[A-Za-z0-9_-]+/[A-Za-z0-9._-]+$")


def sanear_nombre(nombre_archivo: str) -> str:
    base = os.path.basename(nombre_archivo.replace("\\", "/")).strip()
    base = _NOMBRE_SEGURO.sub("_", base).strip("._")
    return base or "archivo"


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode().rstrip("=")


def _unb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


class StorageLocal:
    def __init__(
        self,
        directorio: str | os.PathLike | None = None,
        secreto: str | None = None,
        base_url: str | None = None,
    ):
        self.directorio = Path(directorio or settings.storage_local_dir).resolve()
        self.secreto = (secreto or settings.storage_secret).encode()
        self.base_url = (base_url or settings.storage_local_base_url).rstrip("/")

    # --- contrato -----------------------------------------------------------------
    def clave_para(self, tenant_id: str, documento_id: str, nombre_archivo: str) -> str:
        return f"{tenant_id}/{documento_id}/{sanear_nombre(nombre_archivo)}"

    def url_prefirmada_put(self, clave: str, content_type: str, expira_seg: int, max_bytes: int) -> str:
        if not content_type or max_bytes <= 0:
            raise ValueError("content_type y max_bytes son obligatorios para firmar una subida")
        return f"{self.base_url}/{self.firmar(clave, 'put', expira_seg, content_type=content_type, max_bytes=max_bytes)}"

    def url_prefirmada_get(self, clave: str, expira_seg: int) -> str:
        return f"{self.base_url}/{self.firmar(clave, 'get', expira_seg)}"

    def existe(self, clave: str) -> bool:
        return self.ruta(clave).is_file()

    def inspeccionar(self, clave: str) -> InfoArchivo | None:
        ruta = self.ruta(clave)
        if not ruta.is_file():
            return None
        h = hashlib.sha256()
        total = 0
        with ruta.open("rb") as f:
            for bloque in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloque)
                total += len(bloque)
        return InfoArchivo(bytes=total, checksum_sha256=h.hexdigest())

    def borrar(self, clave: str) -> bool:
        ruta = self.ruta(clave)
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            return False
        return not ruta.exists()

    def disponible(self) -> bool:
        """El directorio existe (o se puede crear) y admite escritura real."""
        try:
            self.directorio.mkdir(parents=True, exist_ok=True)
            sonda = self.directorio / f".readiness-{os.getpid()}"
            sonda.write_bytes(b"ok")
            leido = sonda.read_bytes()
            sonda.unlink(missing_ok=True)
            return leido == b"ok"
        except OSError:
            return False

    # --- firma --------------------------------------------------------------------
    @staticmethod
    def tenant_de_clave(clave: str) -> str:
        return clave.split("/", 1)[0]

    def ruta(self, clave: str) -> Path:
        if not _CLAVE_VALIDA.match(clave):
            raise Prohibido("Clave de storage inválida")
        ruta = (self.directorio / clave).resolve()
        if self.directorio not in ruta.parents:
            raise Prohibido("Clave de storage fuera del directorio base")
        return ruta

    def firmar(
        self,
        clave: str,
        operacion: str,
        expira_seg: int,
        content_type: str | None = None,
        ahora: datetime | None = None,
        max_bytes: int | None = None,
    ) -> str:
        if expira_seg <= 0:
            raise ValueError("expira_seg debe ser positivo")
        self.ruta(clave)  # forma válida antes de firmar nada
        exp = (ahora or ahora_utc()) + timedelta(seconds=expira_seg)
        cuerpo: dict[str, Any] = {
            "clave": clave,
            "tenant": self.tenant_de_clave(clave),
            "op": operacion,
            "exp": int(exp.timestamp()),
        }
        if content_type:
            cuerpo["ct"] = content_type
        if max_bytes:
            cuerpo["max"] = int(max_bytes)
        datos = _b64(json.dumps(cuerpo, separators=(",", ":"), sort_keys=True).encode())
        return f"{datos}.{self._mac(datos)}"

    def _mac(self, datos: str) -> str:
        return hmac.new(self.secreto, datos.encode(), hashlib.sha256).hexdigest()

    def verificar(self, firma: str, operacion: str, ahora: datetime | None = None) -> dict[str, Any]:
        """Devuelve el cuerpo de la firma si es válida; si no, `Prohibido`. Chequea HMAC,
        vencimiento, operación y que la clave pertenezca al tenant de la firma."""
        try:
            datos, mac = firma.split(".", 1)
        except ValueError:
            raise Prohibido("Firma de storage inválida")
        if not hmac.compare_digest(mac, self._mac(datos)):
            raise Prohibido("Firma de storage inválida")
        try:
            cuerpo = json.loads(_unb64(datos))
        except Exception:
            raise Prohibido("Firma de storage inválida")
        instante = ahora or ahora_utc()
        if datetime.fromtimestamp(int(cuerpo.get("exp", 0)), tz=timezone.utc) < instante:
            raise Prohibido("La URL firmada venció")
        if cuerpo.get("op") != operacion:
            raise Prohibido("La URL firmada no habilita esta operación")
        clave = cuerpo.get("clave", "")
        if not clave or self.tenant_de_clave(clave) != cuerpo.get("tenant"):
            raise Prohibido("La URL firmada no corresponde a este tenant")
        self.ruta(clave)  # valida forma y traversal
        return cuerpo

    # --- IO -----------------------------------------------------------------------
    def escribir(self, clave: str, contenido: bytes) -> str:
        ruta = self.ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)
        return hashlib.sha256(contenido).hexdigest()

    def leer(self, clave: str) -> bytes:
        return self.ruta(clave).read_bytes()
