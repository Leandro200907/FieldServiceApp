"""Storage de desarrollo sobre filesystem con URLs firmadas HMAC.

La "URL prefirmada" local es `{base_url}/{firma}` donde `firma` es un token
`base64url(json) . hmac_sha256` que lleva clave, tenant, operación (put/get),
content_type (solo put) y vencimiento. `app/storage/router.py` la valida y sirve el
archivo. La firma nunca se persiste: se deriva cada vez.

Configuración por env (no se toca app/config.py — ver informe):
  STORAGE_LOCAL_DIR       directorio base (default ./storage_local)
  STORAGE_LOCAL_BASE_URL  prefijo de las URLs (default /v1/storage)
El secreto de firma es `settings.jwt_secret`.
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
        self.directorio = Path(directorio or os.environ.get("STORAGE_LOCAL_DIR", "./storage_local")).resolve()
        self.secreto = (secreto or settings.jwt_secret).encode()
        self.base_url = (base_url or os.environ.get("STORAGE_LOCAL_BASE_URL", "/v1/storage")).rstrip("/")

    # --- contrato -----------------------------------------------------------------
    def clave_para(self, tenant_id: str, documento_id: str, nombre_archivo: str) -> str:
        return f"{tenant_id}/{documento_id}/{sanear_nombre(nombre_archivo)}"

    def url_prefirmada_put(self, clave: str, content_type: str, expira_seg: int) -> str:
        return f"{self.base_url}/{self.firmar(clave, 'put', expira_seg, content_type=content_type)}"

    def url_prefirmada_get(self, clave: str, expira_seg: int) -> str:
        return f"{self.base_url}/{self.firmar(clave, 'get', expira_seg)}"

    def existe(self, clave: str) -> bool:
        return self.ruta(clave).is_file()

    def borrar(self, clave: str) -> bool:
        ruta = self.ruta(clave)
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            return False
        return not ruta.exists()

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
    ) -> str:
        if expira_seg <= 0:
            raise ValueError("expira_seg debe ser positivo")
        exp = (ahora or ahora_utc()) + timedelta(seconds=expira_seg)
        cuerpo: dict[str, Any] = {
            "clave": clave,
            "tenant": self.tenant_de_clave(clave),
            "op": operacion,
            "exp": int(exp.timestamp()),
        }
        if content_type:
            cuerpo["ct"] = content_type
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
