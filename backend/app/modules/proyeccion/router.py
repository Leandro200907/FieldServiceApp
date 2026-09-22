"""GET /v1/consultas/calendario_vigencias, proyeccion_documental_backlog y
proyeccion_documental (docs/PROYECCION_DOCUMENTAL.md)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.proyeccion import servicio

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


# --------------------------------------------------------------------------- proyeccion_documental


class SujetosOrigen(BaseModel):
    origen: Literal["ultima_decision_visible", "candidatos_del_alcance"]
    referencia_evaluacion: str | None
    evaluada_en: datetime | None
    sujeto_ids: list[str]


class OcInfo(BaseModel):
    cliente_id: str
    locacion_id: str
    tipo_servicio_id: str
    vigencia_desde: date
    vigencia_hasta: date


class MatrizInfo(BaseModel):
    matriz_version_id: str
    version: int
    tipos_exigidos: list[str]


class CausaProyeccion(BaseModel):
    motivo: str
    tipo_sujeto: str | None = None
    requisito_definicion_id: str | None = None
    sujetos_que_pierden_cobertura: list[str] | None = None
    sujetos_que_mantienen_cobertura: list[str] | None = None


class IntervaloProyeccion(BaseModel):
    desde: date
    hasta: date
    estado: Literal["bloqueo_confirmado", "requiere_revision", "sin_riesgos_detectados"]
    capacidad_documental_potencial: dict[str, int]
    causas: list[CausaProyeccion] | None = None


class ProyeccionDocumentalResponse(BaseModel):
    commitment_id: str
    oc: OcInfo
    hoy: date
    desde: date
    hasta: date
    sujetos: SujetosOrigen
    matriz: MatrizInfo | None
    estado: Literal["sin_matriz", "pendiente_de_planificacion", "bloqueo_confirmado",
                    "requiere_revision", "riesgo_documental", "sin_riesgos_detectados"]
    intervalos: list[IntervaloProyeccion]
    causas: list[CausaProyeccion] | None = None
    estado_por_dia: dict[str, str] | None = None
    advertencia: str


@router.get("/consultas/proyeccion_documental", response_model=ProyeccionDocumentalResponse)
def proyeccion_documental(
    commitment_id: str = Query(...), desde: date | None = Query(None), hasta: date | None = Query(None),
    detalle: Literal["resumen", "diario"] = Query("resumen"),
    identidad: Identidad = Depends(identidad_actual),
) -> ProyeccionDocumentalResponse:
    with tenant_session(identidad.tenant_id) as s:
        return ProyeccionDocumentalResponse(**servicio.proyeccion_documental(
            s, identidad, commitment_id, desde=desde, hasta=hasta, detalle=detalle,
        ))


# --------------------------------------------------------------------------- proyeccion_documental_backlog


class ItemBacklog(BaseModel):
    commitment_id: str
    vigencia_desde: date
    vigencia_hasta: date
    estado: Literal["sin_matriz", "pendiente_de_planificacion", "bloqueo_confirmado",
                    "requiere_revision", "riesgo_documental", "sin_riesgos_detectados"]
    primer_quiebre: date | None
    capacidad_documental_potencial_hoy: dict[str, int]
    origen_calculo: Literal["ultima_decision_visible", "candidatos_del_alcance"]
    motivos_resumidos: list[str]


class ProyeccionDocumentalBacklogResponse(BaseModel):
    hoy: date
    horizonte_dias: int
    items: list[ItemBacklog]
    total: int
    offset: int
    limit: int
    advertencia: str


@router.get("/consultas/proyeccion_documental_backlog", response_model=ProyeccionDocumentalBacklogResponse)
def proyeccion_documental_backlog(
    estado_oc: Literal["activo", "cancelado"] = Query("activo"),
    estado: list[str] | None = Query(None),
    horizonte_dias: int = Query(30, ge=1),
    identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina),
) -> ProyeccionDocumentalBacklogResponse:
    with tenant_session(identidad.tenant_id) as s:
        return ProyeccionDocumentalBacklogResponse(**servicio.proyeccion_documental_backlog(
            s, identidad, p, estado_oc=estado_oc, estados=estado, horizonte_dias=horizonte_dias,
        ))
