"""Alertas de vencimiento: comandos (configurar, reconocer) y consultas (abiertas,
historial, configuración). Permisos: matriz 2.2 + alcance por rol (2.3)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

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


@router.post("/comandos/configurar_alertas")
def configurar_alertas(body: ConfigurarAlertasBody, identidad: Identidad = Depends(identidad_actual),
                       clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: servicio.configurar(s, identidad, **body.model_dump()),
                            ruta="/comandos/configurar_alertas", body=body.model_dump(mode="json"))


@router.post("/comandos/reconocer_alerta")
def reconocer_alerta(body: ReconocerAlertaBody, identidad: Identidad = Depends(identidad_actual),
                     clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.SUPERVISOR, Rol.RESPONSABLE_LEGAJOS), lambda s: servicio.reconocer(s, identidad, **body.model_dump()),
                            ruta="/comandos/reconocer_alerta", body=body.model_dump(mode="json"))


@router.get("/consultas/alertas_abiertas")
def alertas_abiertas(sujeto_id: str | None = Query(None), etapa: Literal["aviso", "recordatorio", "vencido", "escalado"] | None = Query(None),
                     identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.alertas_abiertas(s, identidad, p, sujeto_id, etapa)


@router.get("/consultas/historial_alertas")
def historial_alertas(sujeto_id: str | None = Query(None), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.historial_alertas(s, identidad, p, sujeto_id)


@router.get("/consultas/configuracion_alertas")
def configuracion_alertas(identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.configuracion(s, identidad)
