"""Puerto de carpeta de solo lectura (anexo v1: "conexión de solo lectura a una carpeta de
Drive, un único proveedor") y adaptadores: Google Drive (API v3, cuenta de servicio) y
un proveedor en memoria para tests.

Google Drive: la cuenta de servicio (JSON) vive SOLO en la variable de entorno de la
plataforma `DRIVE_SERVICE_ACCOUNT_JSON` (o `DRIVE_SERVICE_ACCOUNT_FILE`); el tenant comparte
su carpeta con el mail de esa cuenta y configura sólo el `carpeta_id`. Pull job del
backend con sus propias credenciales (8.5): nunca URL firmada de cliente. Sólo lectura:
scope `drive.readonly`.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import httpx


@dataclass(frozen=True)
class ArchivoRemoto:
    id_externo: str
    nombre: str
    mime: str | None
    modificado: datetime | None
    hash: str | None   # md5 que informa el proveedor (o None)
    bytes: int | None


class ProveedorDeCarpeta(Protocol):
    nombre: str

    def listar(self, carpeta_id: str) -> list[ArchivoRemoto]: ...

    def descargar(self, id_externo: str, max_bytes: int) -> bytes: ...


class ProveedorNoDisponible(Exception):
    pass


class GoogleDrive:
    nombre = "google_drive"
    SCOPE = "https://www.googleapis.com/auth/drive.readonly"

    def __init__(self, credenciales: dict | None = None, cliente: httpx.Client | None = None):
        self._cred = credenciales or self._cred_de_entorno()
        self._cliente = cliente or httpx.Client(timeout=30)
        self._token: tuple[str, float] | None = None

    @staticmethod
    def _cred_de_entorno() -> dict | None:
        raw = os.environ.get("DRIVE_SERVICE_ACCOUNT_JSON")
        if raw:
            return json.loads(raw)
        ruta = os.environ.get("DRIVE_SERVICE_ACCOUNT_FILE")
        if ruta and os.path.isfile(ruta):
            return json.loads(open(ruta, encoding="utf-8").read())
        return None

    def _access_token(self) -> str:
        if self._cred is None:
            raise ProveedorNoDisponible("Drive: falta DRIVE_SERVICE_ACCOUNT_JSON / DRIVE_SERVICE_ACCOUNT_FILE")
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        import jwt as pyjwt

        ahora = int(time.time())
        asercion = pyjwt.encode(
            {"iss": self._cred["client_email"], "scope": self.SCOPE, "aud": self._cred.get("token_uri", "https://oauth2.googleapis.com/token"),
             "iat": ahora, "exp": ahora + 3600},
            self._cred["private_key"], algorithm="RS256",
        )
        r = self._cliente.post(self._cred.get("token_uri", "https://oauth2.googleapis.com/token"),
                               data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": asercion})
        r.raise_for_status()
        datos = r.json()
        self._token = (datos["access_token"], time.time() + int(datos.get("expires_in", 3600)))
        return self._token[0]

    def listar(self, carpeta_id: str) -> list[ArchivoRemoto]:
        salida: list[ArchivoRemoto] = []
        token = self._access_token()
        pagina = None
        while True:
            params = {"q": f"'{carpeta_id}' in parents and trashed = false", "pageSize": 200,
                      "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, md5Checksum, size)", "supportsAllDrives": "true",
                      "includeItemsFromAllDrives": "true"}
            if pagina:
                params["pageToken"] = pagina
            r = self._cliente.get("https://www.googleapis.com/drive/v3/files", params=params, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            datos = r.json()
            for f in datos.get("files", []):
                mod = datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")) if f.get("modifiedTime") else None
                salida.append(ArchivoRemoto(f["id"], f["name"], f.get("mimeType"), mod, f.get("md5Checksum"), int(f["size"]) if f.get("size") else None))
            pagina = datos.get("nextPageToken")
            if not pagina:
                return salida

    def descargar(self, id_externo: str, max_bytes: int) -> bytes:
        token = self._access_token()
        with self._cliente.stream("GET", f"https://www.googleapis.com/drive/v3/files/{id_externo}", params={"alt": "media", "supportsAllDrives": "true"},
                                  headers={"Authorization": f"Bearer {token}"}) as r:
            r.raise_for_status()
            partes: list[bytes] = []
            total = 0
            for chunk in r.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("archivo_demasiado_grande")
                partes.append(chunk)
        return b"".join(partes)


@dataclass
class ProveedorEnMemoria:
    """Tests: carpeta simulada `{carpeta_id: [ArchivoRemoto]}` y contenidos por id."""
    nombre: str = "memoria"
    carpetas: dict[str, list[ArchivoRemoto]] = field(default_factory=dict)
    contenidos: dict[str, bytes] = field(default_factory=dict)
    descargas: list[str] = field(default_factory=list)

    def listar(self, carpeta_id: str) -> list[ArchivoRemoto]:
        if carpeta_id not in self.carpetas:
            raise ProveedorNoDisponible("carpeta inexistente o sin permiso")
        return list(self.carpetas[carpeta_id])

    def descargar(self, id_externo: str, max_bytes: int) -> bytes:
        self.descargas.append(id_externo)
        datos = self.contenidos[id_externo]
        if len(datos) > max_bytes:
            raise ValueError("archivo_demasiado_grande")
        return datos


def proveedor_de_plataforma() -> ProveedorDeCarpeta:
    return GoogleDrive()
