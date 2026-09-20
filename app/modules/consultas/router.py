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
def cobertura_oc(commitment_id: str = Query(...), identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.cobertura_oc(s, identidad, commitment_id)


@router.get("/consultas/decisiones_oc")
def decisiones_oc(
    commitment_id: str = Query(...), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.decisiones_oc(s, identidad, commitment_id, p)


@router.get("/consultas/decision")
def decision(referencia_evaluacion: str = Query(...), identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.decision(s, identidad, referencia_evaluacion)


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


@router.get("/consultas/incumplimiento_empresa")
def incumplimiento_empresa(identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.incumplimiento_empresa(s, identidad)


@router.get("/consultas/plantillas_globales")
def plantillas_globales(identidad: Identidad = Depends(identidad_actual)) -> dict:
    """Plantillas de industria junto a las copias locales (estado sin_copia / al_dia /
    actualizacion_disponible) para decidir a mano qué traer (no-funcionales 1.5.3)."""
    from app.modules.requisitos.plantillas import plantillas_globales as _consulta
    with tenant_session(identidad.tenant_id) as s:
        return _consulta(s, identidad)


# --------------------------------------------------------------------------- H-05 / H-06
from typing import Literal  # noqa: E402

from app.modules.consultas import catalogos  # noqa: E402


def _con(fn, identidad, **kw):
    with tenant_session(identidad.tenant_id) as s:
        return fn(s, identidad, **kw)


@router.get("/consultas/mi_legajo")
def mi_legajo(identidad: Identidad = Depends(identidad_actual)) -> dict:
    """Legajo compuesto del técnico: su persona + vehículos/equipos bajo su custodia vigente (H-05)."""
    return _con(catalogos.mi_legajo, identidad)


@router.get("/consultas/sujetos")
def sujetos(q: str | None = Query(None, max_length=200), tipo_sujeto: Literal["empresa", "persona", "vehiculo", "equipo"] | None = Query(None),
            activos: bool | None = Query(True), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.sujetos, identidad, p=p, q=q, tipo_sujeto=tipo_sujeto, activos=activos)


@router.get("/consultas/definiciones_requisito")
def definiciones_requisito(q: str | None = Query(None, max_length=200), categoria: Literal["documento", "competencia", "induccion"] | None = Query(None),
                           tipo_sujeto_aplicable: Literal["empresa", "persona", "vehiculo", "equipo"] | None = Query(None),
                           activas: bool | None = Query(True), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.definiciones_requisito, identidad, p=p, q=q, categoria=categoria, tipo_sujeto_aplicable=tipo_sujeto_aplicable, activas=activas)


@router.get("/consultas/matrices")
def matrices(cliente_id: UUID | None = Query(None), solo_vigentes: bool = Query(False),
             identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.matrices, identidad, p=p, cliente_id=str(cliente_id) if cliente_id else None, solo_vigentes=solo_vigentes)


@router.get("/consultas/usuarios")
def usuarios(q: str | None = Query(None, max_length=200), rol: Literal["configuracion", "responsable_legajos", "supervisor", "tecnico"] | None = Query(None),
             activos: bool | None = Query(True), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.usuarios, identidad, p=p, q=q, rol=rol, activos=activos)


@router.get("/consultas/documentos")
def documentos(sujeto_id: str | None = Query(None), estado_version: Literal["vigente", "sucedida", "rechazada", "revertida_por_lote", "todas"] = Query("vigente"),
               estado_confirmacion: Literal["declarado", "verificado", "confirmado_en_fuente"] | None = Query(None),
               archivo_estado: str | None = Query(None, max_length=40), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.documentos, identidad, p=p, sujeto_id=sujeto_id, estado_version=None if estado_version == "todas" else estado_version,
                estado_confirmacion=estado_confirmacion, archivo_estado=archivo_estado)


@router.get("/consultas/excepciones")
def excepciones(sujeto_id: str | None = Query(None), estado: Literal["otorgada", "revocada", "regularizada", "vencida"] | None = Query("otorgada"),
                commitment_id: str | None = Query(None), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.excepciones, identidad, p=p, sujeto_id=sujeto_id, estado=estado, commitment_id=commitment_id)


@router.get("/consultas/constancias")
def constancias(sujeto_id: str | None = Query(None), estado: Literal["vigente", "vencida", "revocada", "reemplazada"] | None = Query("vigente"),
                cliente_id: UUID | None = Query(None), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.constancias, identidad, p=p, sujeto_id=sujeto_id, estado=estado, cliente_id=str(cliente_id) if cliente_id else None)


@router.get("/consultas/custodias")
def custodias(recurso_id: str | None = Query(None), custodio_id: str | None = Query(None), solo_vigentes: bool = Query(False),
              identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.custodias, identidad, p=p, recurso_id=recurso_id, custodio_id=custodio_id, solo_vigentes=solo_vigentes)


@router.get("/consultas/lotes")
def lotes(estado: Literal["aplicado", "revertido"] | None = Query(None), entidad: Literal["legajos", "oc"] | None = Query(None),
          identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.lotes, identidad, p=p, estado=estado, entidad=entidad)


@router.get("/consultas/asignaciones_supervisor")
def asignaciones_supervisor(supervisor_usuario_id: UUID | None = Query(None), sujeto_id: str | None = Query(None), solo_vigentes: bool = Query(True),
                            identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    return _con(catalogos.asignaciones_supervisor, identidad, p=p, supervisor_usuario_id=str(supervisor_usuario_id) if supervisor_usuario_id else None,
                sujeto_id=sujeto_id, solo_vigentes=solo_vigentes)
