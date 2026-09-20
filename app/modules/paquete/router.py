"""Paquete de entrega: comandos autenticados + endpoint público firmado (sin JWT)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.db import platform_session, tenant_session
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando
from app.modules.paquete import servicio

router = APIRouter(tags=["paquete"])


class GenerarPaqueteBody(BaseModel):
    sujeto_id: str = Field(min_length=1)
    dias_validez: int = Field(30, ge=1, le=90)


class RevocarPaqueteBody(BaseModel):
    paquete_id: str


@router.post("/comandos/generar_paquete_entrega")
def generar_paquete_entrega(body: GenerarPaqueteBody, request: Request, identidad: Identidad = Depends(identidad_actual),
                            clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    base = str(request.base_url).rstrip("/")
    return ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
                            lambda s: servicio.generar_paquete(s, identidad, sujeto_id=body.sujeto_id, dias_validez=body.dias_validez, base_url=base),
                            ruta="/comandos/generar_paquete_entrega", body=body.model_dump(mode="json"))


@router.post("/comandos/revocar_paquete_entrega")
def revocar_paquete_entrega(body: RevocarPaqueteBody, identidad: Identidad = Depends(identidad_actual),
                            clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,), lambda s: servicio.revocar_paquete(s, identidad, paquete_id=body.paquete_id),
                            ruta="/comandos/revocar_paquete_entrega", body=body.model_dump(mode="json"))


@router.get("/consultas/paquetes_entrega")
def paquetes_entrega(sujeto_id: str | None = Query(None), identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return {"items": servicio.paquetes(s, identidad, sujeto_id)}


# --------------------------------------------------------------------------- público


def _resolver(token: str, request: Request) -> tuple[str, str]:
    origen = request.client.host if request.client else "?"
    if not servicio.limiter.permitir(f"origen:{origen}") or not servicio.limiter.permitir(f"token:{token[:16]}"):
        raise ErrorDeDominio("Demasiadas solicitudes; reintentar en un minuto", codigo="rate_limit")
    token_hash = servicio.verificar_token(token)
    if token_hash is None:
        raise NoEncontrado("Paquete inexistente o vencido")
    with platform_session() as s:
        tenant_id = s.execute(text("SELECT modulo1.resolver_tenant_por_paquete(:h)"), {"h": token_hash}).scalar()
    if tenant_id is None:
        raise NoEncontrado("Paquete inexistente o vencido")
    return str(tenant_id), token_hash


@router.get("/publico/paquete/{token}")
def paquete_publico(token: str, request: Request) -> dict:
    """Sin JWT: quien tiene el link firmado ve el estado de cumplimiento del sujeto (sin archivos)."""
    tenant_id, token_hash = _resolver(token, request)
    with tenant_session(tenant_id) as s:
        return servicio.vista_publica(s, tenant_id, token_hash, request.client.host if request.client else None)


@router.get("/publico/paquete/{token}/qr.png")
def paquete_qr(token: str, request: Request) -> Response:
    tenant_id, token_hash = _resolver(token, request)
    with tenant_session(tenant_id) as s:
        vigente = s.execute(text("SELECT 1 FROM modulo1.paquete_entrega WHERE tenant_id = :t AND token_hash = :h AND revocado_en IS NULL AND expira_en > now()"),
                            {"t": tenant_id, "h": token_hash}).first()
    if vigente is None:
        raise NoEncontrado("Paquete inexistente o vencido")
    url = str(request.base_url).rstrip("/") + f"/v1/publico/paquete/{token}"
    return Response(content=servicio.qr_png(url), media_type="image/png", headers={"Cache-Control": "no-store"})
