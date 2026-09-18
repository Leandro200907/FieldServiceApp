"""GET /v1/consultas/* — lecturas paginadas con `app.comun.paginacion`."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.consultas import servicio

router = APIRouter()


@router.get("/consultas/legajo")
def legajo(sujeto_id: str = Query(...), identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.legajo(s, identidad, sujeto_id)


@router.get("/consultas/propuestas_pendientes")
def propuestas_pendientes(identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.propuestas_pendientes(s, identidad, p)


@router.get("/consultas/tablero_vencimientos")
def tablero_vencimientos(
    dias: int = Query(30, ge=0, le=3650),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.tablero_vencimientos(s, identidad, dias, p)


@router.get("/consultas/backlog_oc")
def backlog_oc(
    estado: str | None = Query("activo"),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.backlog_oc(s, identidad, estado or None, p)


@router.get("/consultas/cobertura_oc")
def cobertura_oc(
    commitment_id: str = Query(...),
    recalcular: bool = Query(False),
    identidad: Identidad = Depends(identidad_actual),
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.cobertura_oc(s, identidad, commitment_id, recalcular)


@router.get("/consultas/historial_supervision")
def historial_supervision(
    sujeto_id: str = Query(...), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.historial_supervision(s, identidad, sujeto_id, p)


@router.get("/consultas/log_auditoria")
def log_auditoria(
    tipo: str | None = Query(None),
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.log_auditoria(s, identidad, tipo, desde, hasta, p)


@router.get("/consultas/matriz_vigente")
def matriz_vigente(
    cliente_id: UUID = Query(...),
    locacion_id: UUID = Query(...),
    tipo_servicio_id: UUID = Query(...),
    fecha: date | None = Query(None),
    identidad: Identidad = Depends(identidad_actual),
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.matriz_vigente(s, identidad, str(cliente_id), str(locacion_id), str(tipo_servicio_id), fecha)
