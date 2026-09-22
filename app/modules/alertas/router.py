"""Alertas de vencimiento: comandos (configurar, reconocer) y consultas (abiertas,
historial, configuración). Permisos: matriz 2.2 + alcance por rol (2.3)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.alertas import servicio
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando

router = APIRouter(tags=["alertas"])


class ConfigurarAlertasBody(BaseModel):
    plazo_aviso_dias: int = Field(30, ge=1, le=365)
    escalamiento_dias: int = Field(7, ge=0, le=365)
    rol_escalamiento: Literal["configuracion", "responsable_legajos", "supervisor"] = "responsable_legajos"
    reconocimiento_dias: int = Field(3, ge=0, le=30)


class ReconocerAlertaBody(BaseModel):
    alerta_id: str
    comentario: str | None = None


class PlazoPorRequisito(BaseModel):
    requisito_definicion_id: str
    nombre: str
    plazo_aviso_dias: int


class ConfiguracionAlertasResponse(BaseModel):
    plazo_aviso_dias: int
    escalamiento_dias: int
    rol_escalamiento: str
    reconocimiento_dias: int
    plazos_por_requisito: list[PlazoPorRequisito]


class ConfigurarAlertasResponse(ConfiguracionAlertasResponse):
    eventos: list[str]


class ReconocerAlertaResponse(BaseModel):
    alerta_id: str
    reconocida_hasta: str
    eventos: list[str]


class AlertaVencimiento(BaseModel):
    alerta_id: str
    fuente_tipo: str
    fuente_id: str
    sujeto_id: str
    tipo_sujeto: str
    requisito_definicion_id: str
    requisito: str
    vigente_hasta: date | None
    etapa: str
    estado: str
    bajo_excepcion: bool
    ultima_accion_tipo: str | None
    ultima_accion_en: datetime | None
    ultima_accion_ref: str | None
    reconocida_hasta: date | None
    destinatarios_notificados_en_esta_etapa: list[str] | None
    abierta_en: date
    etapa_desde: date
    escalada_en: date | None
    resuelta_en: datetime | None
    resuelta_motivo: str | None
    resuelta_ref: str | None


class AlertasAbiertasResponse(BaseModel):
    items: list[AlertaVencimiento]
    total: int
    offset: int
    limit: int
    hoy: str
    por_etapa: dict[str, int]


class EventoAlerta(BaseModel):
    model_config = ConfigDict(extra="allow")

    tipo: str
    en: datetime


class AlertaHistorialItem(AlertaVencimiento):
    eventos: list[EventoAlerta]


class HistorialAlertasResponse(BaseModel):
    items: list[AlertaHistorialItem]
    total: int
    offset: int
    limit: int


@router.post("/comandos/configurar_alertas", response_model=ConfigurarAlertasResponse)
def configurar_alertas(body: ConfigurarAlertasBody, identidad: Identidad = Depends(identidad_actual),
                       clave: str | None = Depends(clave_idempotencia)) -> ConfigurarAlertasResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: servicio.configurar(s, identidad, **body.model_dump()),
                            ruta="/comandos/configurar_alertas", body=body.model_dump(mode="json"))
    return ConfigurarAlertasResponse(**resultado)


@router.post("/comandos/reconocer_alerta", response_model=ReconocerAlertaResponse)
def reconocer_alerta(body: ReconocerAlertaBody, identidad: Identidad = Depends(identidad_actual),
                     clave: str | None = Depends(clave_idempotencia)) -> ReconocerAlertaResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.SUPERVISOR, Rol.RESPONSABLE_LEGAJOS), lambda s: servicio.reconocer(s, identidad, **body.model_dump()),
                            ruta="/comandos/reconocer_alerta", body=body.model_dump(mode="json"))
    return ReconocerAlertaResponse(**resultado)


@router.get("/consultas/alertas_abiertas", response_model=AlertasAbiertasResponse)
def alertas_abiertas(sujeto_id: str | None = Query(None), etapa: Literal["aviso", "recordatorio", "vencido", "escalado"] | None = Query(None),
                     identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> AlertasAbiertasResponse:
    with tenant_session(identidad.tenant_id) as s:
        return AlertasAbiertasResponse(**servicio.alertas_abiertas(s, identidad, p, sujeto_id, etapa))


@router.get("/consultas/historial_alertas", response_model=HistorialAlertasResponse)
def historial_alertas(sujeto_id: str | None = Query(None), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> HistorialAlertasResponse:
    with tenant_session(identidad.tenant_id) as s:
        return HistorialAlertasResponse(**servicio.historial_alertas(s, identidad, p, sujeto_id))


@router.get("/consultas/configuracion_alertas", response_model=ConfiguracionAlertasResponse)
def configuracion_alertas(identidad: Identidad = Depends(identidad_actual)) -> ConfiguracionAlertasResponse:
    with tenant_session(identidad.tenant_id) as s:
        return ConfiguracionAlertasResponse(**servicio.configuracion(s, identidad))
