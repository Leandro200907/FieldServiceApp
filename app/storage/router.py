"""Endpoints del storage local y comandos de evidencia.

- `POST /comandos/preparar_subida_de_evidencia` y `POST /comandos/confirmar_subida_de_evidencia`
  (autenticados): la clave la deriva el servidor; la confirmación mide el archivo real.
- `PUT /storage/{firma}` / `GET /storage/{firma}`: equivalente de desarrollo del bucket.
  La URL prefirmada es el permiso (el cliente que sube desde el navegador no pasa por la
  API), por eso no exigen JWT; la firma lleva tenant, clave, operación, vencimiento y —para
  PUT— Content-Type y tamaño máximo, todos verificados. Si el request igual trae
  Authorization válido, el tenant del token tiene que coincidir con el de la firma.
- `GET /storage/documentos/{documento_id}/url` es DescargarArchivoDeEvidencia (2.2).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.api.errores import ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.auth.jwt import validar_access_token
from app.comun.idempotencia import buscar_resultado, guardar_resultado
from app.db import tenant_session
from app.storage.local import StorageLocal
from app.storage.servicio import confirmar_subida, firmar_descarga, preparar_subida

router = APIRouter(tags=["storage"])
_bearer_opcional = HTTPBearer(auto_error=False)


def _storage() -> StorageLocal:
    return StorageLocal()


def _exigir_tenant_del_token(cred: HTTPAuthorizationCredentials | None, tenant_firma: str) -> None:
    if cred is None or not cred.credentials:
        return
    identidad = validar_access_token(cred.credentials)
    if str(identidad.tenant_id) != str(tenant_firma):
        raise Prohibido("La URL firmada pertenece a otro tenant")


class PrepararSubida(BaseModel):
    documento_id: str = Field(min_length=1)
    nombre_archivo: str = Field(min_length=1, max_length=200)
    content_type: str = Field(min_length=1)


class ConfirmarSubida(BaseModel):
    documento_id: str = Field(min_length=1)


@router.post("/comandos/preparar_subida_de_evidencia")
def preparar_subida_de_evidencia(
    body: PrepararSubida,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.TECNICO)
    with tenant_session(identidad.tenant_id) as s:
        previo = buscar_resultado(s, identidad.tenant_id, idempotency_key)
        if previo is not None:
            return previo
        r = preparar_subida(s, identidad, body.documento_id, body.nombre_archivo, body.content_type, storage=_storage())
        guardar_resultado(s, identidad.tenant_id, idempotency_key, r)
        return r


@router.post("/comandos/confirmar_subida_de_evidencia")
def confirmar_subida_de_evidencia(
    body: ConfirmarSubida,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.TECNICO)
    with tenant_session(identidad.tenant_id) as s:
        previo = buscar_resultado(s, identidad.tenant_id, idempotency_key)
        if previo is not None:
            return previo
        r = confirmar_subida(s, identidad, body.documento_id, storage=_storage())
        guardar_resultado(s, identidad.tenant_id, idempotency_key, r)
        return r


@router.get("/storage/documentos/{documento_id}/url")
def url_de_descarga(documento_id: str, identidad: Identidad = Depends(identidad_actual)) -> dict:
    """DescargarArchivoDeEvidencia: responsable_legajos (todo), supervisor (su universo),
    técnico (solo su propio legajo). Audita en event_log y devuelve la URL efímera."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.TECNICO)
    with tenant_session(identidad.tenant_id) as s:
        url = firmar_descarga(s, identidad, documento_id, storage=_storage())
    return {"documento_id": documento_id, "url": url, "eventos": ["DescargarArchivoDeEvidencia"]}


@router.put("/storage/{firma}")
async def subir(
    firma: str, request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer_opcional)
) -> dict:
    storage = _storage()
    cuerpo = storage.verificar(firma, "put")
    _exigir_tenant_del_token(cred, cuerpo["tenant"])
    ct_esperado = cuerpo.get("ct")
    ct_recibido = (request.headers.get("content-type") or "").split(";")[0].strip()
    if not ct_recibido or ct_recibido != ct_esperado:
        raise Prohibido("Content-Type ausente o distinto al firmado", {"esperado": ct_esperado, "recibido": ct_recibido or None})
    max_bytes = int(cuerpo.get("max") or 0)
    if max_bytes <= 0:
        raise Prohibido("La URL firmada no declara tamaño máximo")
    declarado = request.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > max_bytes:
        raise ErrorDeDominio("Archivo demasiado grande", {"max_bytes": max_bytes}, codigo="archivo_demasiado_grande")
    # Lectura por streaming con tope duro: nunca se materializa más que `max_bytes` en RAM.
    partes: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise ErrorDeDominio("Archivo demasiado grande", {"max_bytes": max_bytes}, codigo="archivo_demasiado_grande")
        partes.append(chunk)
    contenido = b"".join(partes)
    if not contenido:
        raise ErrorDeDominio("Archivo vacío", codigo="archivo_vacio")
    checksum = storage.escribir(cuerpo["clave"], contenido)
    return {"bytes": len(contenido), "checksum_sha256": checksum}


@router.get("/storage/{firma}")
def descargar(firma: str, cred: HTTPAuthorizationCredentials | None = Depends(_bearer_opcional)) -> Response:
    storage = _storage()
    cuerpo = storage.verificar(firma, "get")
    _exigir_tenant_del_token(cred, cuerpo["tenant"])
    ruta = storage.ruta(cuerpo["clave"])
    if not ruta.is_file():
        raise NoEncontrado("El archivo no existe en el storage")
    return FileResponse(ruta, filename=ruta.name)
