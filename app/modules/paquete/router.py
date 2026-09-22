"""Paquete de entrega: comandos autenticados + endpoint público firmado (sin JWT)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.comun.red import origen_real
from app.config import settings
from app.db import platform_session, tenant_session
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando
from app.modules.paquete import servicio

router = APIRouter(tags=["paquete"])


class GenerarPaqueteBody(BaseModel):
    sujeto_id: str = Field(min_length=1)
    dias_validez: int = Field(30, ge=1, le=90)


class RevocarPaqueteBody(BaseModel):
    paquete_id: str


class GenerarPaqueteResponse(BaseModel):
    paquete_id: str
    sujeto_id: str
    url: str
    url_qr: str
    expira_en: str
    eventos: list[str]


class RevocarPaqueteResponse(BaseModel):
    paquete_id: str
    eventos: list[str]


class PaqueteEntrega(BaseModel):
    paquete_id: str
    sujeto_id: str
    creado_por: str | None
    expira_en: datetime
    revocado_en: datetime | None
    accesos: int
    ultimo_acceso_en: datetime | None
    creado_en: datetime
    vigente: bool


class PaquetesEntregaResponse(BaseModel):
    items: list[PaqueteEntrega]


@router.post("/comandos/generar_paquete_entrega", response_model=GenerarPaqueteResponse)
def generar_paquete_entrega(body: GenerarPaqueteBody, request: Request, identidad: Identidad = Depends(identidad_actual),
                            clave: str | None = Depends(clave_idempotencia)) -> GenerarPaqueteResponse:
    base = str(request.base_url).rstrip("/")
    resultado = ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
                            lambda s: servicio.generar_paquete(s, identidad, sujeto_id=body.sujeto_id, dias_validez=body.dias_validez, base_url=base),
                            ruta="/comandos/generar_paquete_entrega", body=body.model_dump(mode="json"))
    return GenerarPaqueteResponse(**resultado)


@router.post("/comandos/revocar_paquete_entrega", response_model=RevocarPaqueteResponse)
def revocar_paquete_entrega(body: RevocarPaqueteBody, identidad: Identidad = Depends(identidad_actual),
                            clave: str | None = Depends(clave_idempotencia)) -> RevocarPaqueteResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,), lambda s: servicio.revocar_paquete(s, identidad, paquete_id=body.paquete_id),
                            ruta="/comandos/revocar_paquete_entrega", body=body.model_dump(mode="json"))
    return RevocarPaqueteResponse(**resultado)


@router.get("/consultas/paquetes_entrega", response_model=PaquetesEntregaResponse)
def paquetes_entrega(sujeto_id: str | None = Query(None), identidad: Identidad = Depends(identidad_actual)) -> PaquetesEntregaResponse:
    with tenant_session(identidad.tenant_id) as s:
        return PaquetesEntregaResponse(items=servicio.paquetes(s, identidad, sujeto_id))


# --------------------------------------------------------------------------- público


def _resolver(token: str, request: Request) -> tuple[str, str]:
    origen = origen_real(request.client.host if request.client else None,
                         request.headers.get("x-forwarded-for"), settings.proxies_confiables)
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


class SujetoPaquete(BaseModel):
    sujeto_id: str
    tipo_sujeto: str
    identificador: str


class RequisitoPaquete(BaseModel):
    requisito: str
    categoria: str
    vigente_hasta: str
    estado: str


class ResumenPaquete(BaseModel):
    vigentes: int
    vencidos: int
    sin_verificar: int


class VistaPublicaPaqueteResponse(BaseModel):
    empresa: str | None
    sujeto: SujetoPaquete
    fecha: str
    expira_en: str
    requisitos: list[RequisitoPaquete]
    resumen: ResumenPaquete


@router.get("/publico/paquete/{token}", response_model=VistaPublicaPaqueteResponse)
def paquete_publico(token: str, request: Request) -> VistaPublicaPaqueteResponse:
    """Sin JWT: quien tiene el link firmado ve el estado de cumplimiento del sujeto (sin archivos)."""
    tenant_id, token_hash = _resolver(token, request)
    origen = origen_real(request.client.host if request.client else None,
                         request.headers.get("x-forwarded-for"), settings.proxies_confiables)
    with tenant_session(tenant_id) as s:
        return VistaPublicaPaqueteResponse(**servicio.vista_publica(s, tenant_id, token_hash, origen))


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
