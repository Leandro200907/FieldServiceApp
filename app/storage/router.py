"""Endpoints del storage local: reciben/sirven archivos contra una URL firmada.

Son el equivalente de desarrollo del bucket: la URL prefirmada es el permiso (no se
exige JWT — el cliente que sube desde el navegador no pasa por la API). Si el request
igual trae Authorization válido, el tenant del token tiene que coincidir con el de la
firma. Además `GET /v1/storage/documentos/{documento_id}/url` es el comando
DescargarArchivoDeEvidencia: autenticado, autoriza por rol/universo y devuelve la URL.

Hay que agregar "app.storage.router" a ROUTERS en app/main.py (archivo compartido).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errores import NoEncontrado, Prohibido
from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.auth.jwt import validar_access_token
from app.db import tenant_session
from app.storage.local import StorageLocal
from app.storage.servicio import firmar_descarga

router = APIRouter(prefix="/storage", tags=["storage"])
_bearer_opcional = HTTPBearer(auto_error=False)


def _storage() -> StorageLocal:
    return StorageLocal()


def _exigir_tenant_del_token(cred: HTTPAuthorizationCredentials | None, tenant_firma: str) -> None:
    if cred is None or not cred.credentials:
        return
    identidad = validar_access_token(cred.credentials)
    if str(identidad.tenant_id) != str(tenant_firma):
        raise Prohibido("La URL firmada pertenece a otro tenant")


@router.get("/documentos/{documento_id}/url")
def url_de_descarga(documento_id: str, identidad: Identidad = Depends(identidad_actual)) -> dict:
    """DescargarArchivoDeEvidencia: responsable_legajos (todo), supervisor (su universo),
    técnico (solo su propio legajo). Audita en event_log y devuelve la URL efímera."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.TECNICO)
    with tenant_session(identidad.tenant_id) as s:
        url = firmar_descarga(
            s, identidad.tenant_id, identidad.usuario_id, documento_id, storage=_storage(), identidad=identidad
        )
    return {"documento_id": documento_id, "url": url, "eventos": ["DescargarArchivoDeEvidencia"]}


@router.put("/{firma}")
async def subir(
    firma: str, request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer_opcional)
) -> dict:
    storage = _storage()
    cuerpo = storage.verificar(firma, "put")
    _exigir_tenant_del_token(cred, cuerpo["tenant"])
    ct_esperado = cuerpo.get("ct")
    ct_recibido = (request.headers.get("content-type") or "").split(";")[0].strip()
    if ct_esperado and ct_recibido and ct_recibido != ct_esperado:
        raise Prohibido("Content-Type distinto al firmado", {"esperado": ct_esperado, "recibido": ct_recibido})
    contenido = await request.body()
    checksum = storage.escribir(cuerpo["clave"], contenido)
    return {"clave_storage": cuerpo["clave"], "bytes": len(contenido), "checksum_sha256": checksum}


@router.get("/{firma}")
def descargar(firma: str, cred: HTTPAuthorizationCredentials | None = Depends(_bearer_opcional)) -> Response:
    storage = _storage()
    cuerpo = storage.verificar(firma, "get")
    _exigir_tenant_del_token(cred, cuerpo["tenant"])
    ruta = storage.ruta(cuerpo["clave"])
    if not ruta.is_file():
        raise NoEncontrado("El archivo no existe en el storage")
    return FileResponse(ruta, filename=ruta.name)
