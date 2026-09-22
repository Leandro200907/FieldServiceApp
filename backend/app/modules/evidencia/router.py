"""Validación técnica de evidencia (reauditoría Fase 2 punto 2): comando manual de
invalidación (Responsable_legajos) y bandeja de seguimiento."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.evidencia import servicio
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando

router = APIRouter(tags=["evidencia"])


class InvalidarEvidenciaBody(BaseModel):
    documento_id: str = Field(min_length=1)
    motivo: str = Field(min_length=1)


class InvalidarEvidenciaResponse(BaseModel):
    documento_id: str
    eventos: list[str]


class DocumentoEnBandeja(BaseModel):
    documento_id: str
    sujeto_id: str
    requisito_definicion_id: str
    estado_confirmacion: str
    archivo_validacion: str | None
    archivo_validacion_motivo: str | None
    archivo_validacion_en: datetime | None
    archivo_scan_estado: str | None
    creado_en: datetime


class BandejaValidacionEvidenciaResponse(BaseModel):
    items: list[DocumentoEnBandeja]
    total: int
    offset: int
    limit: int


@router.post("/comandos/invalidar_evidencia", response_model=InvalidarEvidenciaResponse)
def invalidar_evidencia(
    body: InvalidarEvidenciaBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)
) -> InvalidarEvidenciaResponse:
    resultado = ejecutar_comando(
        identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
        lambda s: servicio.invalidar_evidencia_verificada(s, identidad, **body.model_dump()),
        ruta="/comandos/invalidar_evidencia", body=body.model_dump(mode="json"),
    )
    return InvalidarEvidenciaResponse(**resultado)


@router.get("/consultas/bandeja_validacion_evidencia", response_model=BandejaValidacionEvidenciaResponse)
def bandeja_validacion_evidencia(
    estado: Literal["accion_requerida", "pendiente", "valido", "invalido", "todos"] | None = Query(None),
    identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina),
) -> BandejaValidacionEvidenciaResponse:
    with tenant_session(identidad.tenant_id) as s:
        return BandejaValidacionEvidenciaResponse(**servicio.bandeja(s, identidad, p, estado))
