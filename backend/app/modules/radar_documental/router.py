"""Consultas nuevas del radar documental del backlog."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.radar_documental import servicio

router = APIRouter(tags=["radar_documental"])


class ConteoTipo(BaseModel):
    total: int
    con_alertas: int
    incompletos: int


class ItemRadar(BaseModel):
    oc_id: str
    clave_origen: str
    referencia: str | None
    cliente_id: str
    locacion_id: str
    tipo_servicio_id: str
    vigencia_desde: date
    vigencia_hasta: date
    estado_documental: Literal["sin_alertas_documentales", "con_alertas_documentales", "informacion_incompleta", "sin_matriz"]
    primer_quiebre: date | None
    resumen: dict[str, ConteoTipo]
    motivos_resumidos: list[str]


class RadarBacklogResponse(BaseModel):
    calculado_en: datetime
    desde: date
    hasta: date
    items: list[ItemRadar]
    total: int
    offset: int
    limit: int
    advertencia: str


class DetalleOcResponse(BaseModel):
    oc: dict[str, Any]
    estado_documental: str
    matrices_utilizadas: list[dict[str, Any]]
    requisitos_particulares: list[dict[str, Any]]
    grupos: list[dict[str, Any]]
    advertencia: str


class DetalleLegajoResponse(BaseModel):
    oc: dict[str, Any]
    legajo: dict[str, Any]
    advertencia: str


@router.get("/consultas/radar_documental_backlog", response_model=RadarBacklogResponse)
def radar_documental_backlog(
    desde: date | None = Query(None), hasta: date | None = Query(None),
    cliente_id: UUID | None = Query(None), locacion_id: UUID | None = Query(None),
    tipo_servicio_id: UUID | None = Query(None), estado: list[str] | None = Query(None),
    q: str | None = Query(None), identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> RadarBacklogResponse:
    with tenant_session(identidad.tenant_id) as session:
        resultado = servicio.radar_backlog(
            session, identidad, p, desde=desde, hasta=hasta, estados=estado,
            cliente_id=str(cliente_id) if cliente_id else None,
            locacion_id=str(locacion_id) if locacion_id else None,
            tipo_servicio_id=str(tipo_servicio_id) if tipo_servicio_id else None, q=q,
        )
    return RadarBacklogResponse(**resultado)


@router.get("/consultas/radar_documental_oc", response_model=DetalleOcResponse)
def radar_documental_oc(
    oc_id: UUID = Query(...), identidad: Identidad = Depends(identidad_actual),
) -> DetalleOcResponse:
    with tenant_session(identidad.tenant_id) as session:
        return DetalleOcResponse(**servicio.detalle_oc(session, identidad, str(oc_id)))


@router.get("/consultas/radar_documental_oc/{oc_id}/legajos/{sujeto_id}", response_model=DetalleLegajoResponse)
def radar_documental_legajo(
    oc_id: UUID, sujeto_id: str, identidad: Identidad = Depends(identidad_actual),
) -> DetalleLegajoResponse:
    with tenant_session(identidad.tenant_id) as session:
        return DetalleLegajoResponse(**servicio.detalle_legajo(session, identidad, str(oc_id), sujeto_id))

