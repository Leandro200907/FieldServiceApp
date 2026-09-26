"""Consultas informativas del calendario y del radar documental."""
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
from app.modules.proyeccion import servicio
from app.modules.proyeccion import radar

router = APIRouter(tags=["proyeccion"])


# --------------------------------------------------------------------------- calendario_vigencias


class ItemCalendario(BaseModel):
    categoria: str
    id: str
    sujeto_id: str
    tipo_sujeto: str
    identificador_natural: str | None
    requisito_definicion_id: str | None
    requisito: str | None
    vigente_desde: date
    vigente_hasta: date
    estado_confirmacion: str
    archivo_validacion: str | None
    dias_para_vencer: int
    referencia: str


class CalendarioVigenciasResponse(BaseModel):
    hoy: date
    desde: date
    hasta: date
    items: list[ItemCalendario]
    total: int
    offset: int
    limit: int
    advertencia: str


@router.get("/consultas/calendario_vigencias", response_model=CalendarioVigenciasResponse)
def calendario_vigencias(
    desde: date | None = Query(None), hasta: date | None = Query(None),
    tipo_sujeto: Literal["persona", "vehiculo", "equipo", "empresa"] | None = Query(None),
    categoria: Literal["documento", "competencia", "induccion"] | None = Query(None),
    estado: Literal["vigente", "vencido", "todos"] = Query("todos"),
    q: str | None = Query(None),
    identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina),
) -> CalendarioVigenciasResponse:
    with tenant_session(identidad.tenant_id) as s:
        return CalendarioVigenciasResponse(**servicio.calendario_vigencias(
            s, identidad, p, desde=desde, hasta=hasta, tipo_sujeto=tipo_sujeto,
            categoria=categoria, estado=estado, q=q,
        ))


# --------------------------------------------------------------------------- radar documental definitivo


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


class DetalleOcRadarResponse(BaseModel):
    oc: dict[str, Any]
    estado_documental: str
    matrices_utilizadas: list[dict[str, Any]]
    requisitos_particulares: list[dict[str, Any]]
    grupos: list[dict[str, Any]]
    advertencia: str


class DetalleLegajoRadarResponse(BaseModel):
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
        resultado = radar.radar_backlog(
            session, identidad, p, desde=desde, hasta=hasta, estados=estado,
            cliente_id=str(cliente_id) if cliente_id else None,
            locacion_id=str(locacion_id) if locacion_id else None,
            tipo_servicio_id=str(tipo_servicio_id) if tipo_servicio_id else None, q=q,
        )
    return RadarBacklogResponse(**resultado)


@router.get("/consultas/radar_documental_oc", response_model=DetalleOcRadarResponse)
def radar_documental_oc(
    oc_id: UUID = Query(...), identidad: Identidad = Depends(identidad_actual),
) -> DetalleOcRadarResponse:
    with tenant_session(identidad.tenant_id) as session:
        return DetalleOcRadarResponse(**radar.detalle_oc(session, identidad, str(oc_id)))


@router.get("/consultas/radar_documental_oc/{oc_id}/legajos/{sujeto_id}", response_model=DetalleLegajoRadarResponse)
def radar_documental_legajo(
    oc_id: UUID, sujeto_id: str, identidad: Identidad = Depends(identidad_actual),
) -> DetalleLegajoRadarResponse:
    with tenant_session(identidad.tenant_id) as session:
        return DetalleLegajoRadarResponse(**radar.detalle_legajo(session, identidad, str(oc_id), sujeto_id))

