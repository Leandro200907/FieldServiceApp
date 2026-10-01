from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import hashlib

from datetime import date

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.api.errores import ErrorDeDominio
from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando
from app.modules.operadoras import servicio
from app.modules.operadoras.lector_xlsx import leer_planilla

router = APIRouter(tags=["operadoras-documentales"])

_MEDIA_TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _responsable_legajos(identidad: Identidad = Depends(identidad_actual)) -> Identidad:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    return identidad


class RegistrarEstadoOperadoraBody(BaseModel):
    operadora: str = Field(min_length=1, max_length=200)
    sujeto_id: str = Field(min_length=1)
    documento_id: str
    estado: Literal["exportado", "enviado", "aceptado", "rechazado"]
    exportado_en: datetime | None = None
    enviado_en: datetime | None = None
    aceptado_en: datetime | None = None
    rechazado_en: datetime | None = None
    fuente_archivo: str | None = Field(None, max_length=500)
    fuente_hoja: str | None = Field(None, max_length=200)
    fuente_fila: int | None = Field(None, ge=1)
    observacion: str | None = Field(None, max_length=2000)


class RegistrarEstadoOperadoraResponse(BaseModel):
    operadora_id: str
    documento_id: str
    estado: str
    alerta: dict[str, Any] | None
    eventos: list[str]


class AlertaOperadora(BaseModel):
    alerta_id: str
    sujeto_id: str
    identificador_natural: str
    requisito_definicion_id: str
    requisito: str
    operadora_id: str
    operadora: str
    documento_vigente_id: str
    ultimo_documento_operadora_id: str | None
    estado: str
    motivo: str
    abierta_en: datetime
    actualizada_en: datetime


class AlertasOperadoraResponse(BaseModel):
    items: list[AlertaOperadora]
    total: int
    offset: int
    limit: int


class PasoHistorialOperadora(BaseModel):
    estado: str
    paso_en: str
    observacion: str | None
    registrado_por: str
    registrado_nombre: str
    origen: str
    fuente_archivo: str | None
    fuente_hoja: str | None
    fuente_fila: int | None


class VersionHistorialOperadora(BaseModel):
    documento_id: str
    vigente_desde: str
    vigente_hasta: str
    pasos: list[PasoHistorialOperadora]


class HistorialOperadoraResponse(BaseModel):
    operadora_id: str
    sujeto_id: str
    requisito_definicion_id: str
    versiones: list[VersionHistorialOperadora]


class EspejoOperadoraItem(BaseModel):
    alerta_id: str | None
    sujeto_id: str
    identificador_natural: str
    tipo_sujeto: str
    requisito_definicion_id: str
    requisito: str
    operadora_id: str
    operadora: str
    documento_vigente_id: str
    ultimo_documento_operadora_id: str | None
    estado_operadora: str
    motivo: str
    ultimo_movimiento_en: datetime


class EspejoOperadoraResponse(BaseModel):
    items: list[EspejoOperadoraItem]
    total: int
    offset: int
    limit: int


class ResultadoFilaImportada(BaseModel):
    fila: int
    documento_id: str
    operadora_id: str
    estado: str


class ErrorFilaImportada(BaseModel):
    fila: int | None
    codigo: str
    mensaje: str
    detalles: dict[str, Any] | None


class ImportarPlanillaOperadorasResponse(BaseModel):
    archivo: str
    hoja: str
    filas_totales: int
    filas_aceptadas: int
    filas_rechazadas: int
    resultados: list[ResultadoFilaImportada]
    errores: list[ErrorFilaImportada]
    eventos: list[str]


@router.post("/comandos/registrar_estado_documento_operadora", response_model=RegistrarEstadoOperadoraResponse)
def registrar_estado_documento_operadora(
    body: RegistrarEstadoOperadoraBody,
    identidad: Identidad = Depends(identidad_actual),
    clave: str | None = Depends(clave_idempotencia),
) -> RegistrarEstadoOperadoraResponse:
    datos = body.model_dump(mode="json")
    resultado = ejecutar_comando(
        identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
        lambda s: servicio.registrar_estado(s, identidad, **body.model_dump()),
        ruta="/comandos/registrar_estado_documento_operadora", body=datos,
    )
    return RegistrarEstadoOperadoraResponse(**resultado)


@router.post("/comandos/importar_planilla_operadoras", response_model=ImportarPlanillaOperadorasResponse)
def importar_planilla_operadoras(
    identidad: Identidad = Depends(_responsable_legajos),
    clave: str | None = Depends(clave_idempotencia),
    contenido: bytes = Body(media_type=_MEDIA_TYPE_XLSX, max_length=5 * 1024 * 1024),
    nombre_archivo: str = Header("presentaciones_operadoras.xlsx", alias="X-Nombre-Archivo", max_length=500),
    content_type: str = Header(_MEDIA_TYPE_XLSX, alias="Content-Type"),
    hoja: str = Query("Presentaciones", min_length=1, max_length=200),
) -> ImportarPlanillaOperadorasResponse:
    if content_type.split(";")[0].strip().lower() != _MEDIA_TYPE_XLSX:
        raise HTTPException(
            status_code=415,
            detail="Se requiere Content-Type application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    filas, errores_lectura = leer_planilla(contenido, hoja=hoja)
    if errores_lectura and not filas:
        raise ErrorDeDominio(
            "La planilla tiene filas con errores de formato",
            {"errores": errores_lectura},
            codigo="planilla_invalida",
        )
    huella = hashlib.sha256(contenido).hexdigest()
    resultado = ejecutar_comando(
        identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
        lambda s: servicio.importar_filas(
            s, identidad, archivo=nombre_archivo, hoja=hoja, filas=filas, errores_lectura=errores_lectura,
        ),
        ruta="/comandos/importar_planilla_operadoras",
        body={"archivo": nombre_archivo, "hoja": hoja, "sha256": huella},
    )
    return ImportarPlanillaOperadorasResponse.model_validate(resultado)


@router.get("/consultas/alertas_actualizacion_operadora", response_model=AlertasOperadoraResponse)
def alertas_actualizacion_operadora(
    sujeto_id: str | None = Query(None),
    estado: Literal["pendiente_envio", "pendiente_aceptacion", "rechazado"] | None = Query(None),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> AlertasOperadoraResponse:
    with tenant_session(identidad.tenant_id) as session:
        return AlertasOperadoraResponse(**servicio.alertas(session, identidad, p, sujeto_id=sujeto_id, estado=estado))


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/consultas/historial_operadora", response_model=HistorialOperadoraResponse)
def historial_operadora(
    response: Response,
    operadora_id: str = Query(...),
    sujeto_id: str = Query(...),
    requisito_definicion_id: str = Query(...),
    identidad: Identidad = Depends(identidad_actual),
) -> HistorialOperadoraResponse:
    _no_store(response)
    with tenant_session(identidad.tenant_id) as session:
        return HistorialOperadoraResponse(**servicio.historial_operadora(
            session, identidad,
            operadora_id=operadora_id,
            sujeto_id=sujeto_id,
            requisito_definicion_id=requisito_definicion_id,
        ))


@router.get("/consultas/espejo_operadora", response_model=EspejoOperadoraResponse)
def espejo_operadora(
    response: Response,
    operadora_id: list[str] | None = Query(None),
    requisito_definicion_id: list[str] | None = Query(None),
    tipo_sujeto: Literal["persona", "vehiculo", "equipo", "empresa"] | None = Query(None),
    q: str | None = Query(None, min_length=1, max_length=200),
    estado_operadora: list[Literal["pendiente_envio", "pendiente_aceptacion", "rechazado", "al_dia"]] | None = Query(None),
    movimiento_desde: date | None = Query(None),
    movimiento_hasta: date | None = Query(None),
    mes: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> EspejoOperadoraResponse:
    _no_store(response)
    with tenant_session(identidad.tenant_id) as session:
        return EspejoOperadoraResponse(**servicio.listar_espejo_operadora(
            session, identidad, p,
            operadora_id=operadora_id,
            requisito_definicion_id=requisito_definicion_id,
            tipo_sujeto=tipo_sujeto,
            q=q,
            estado_operadora=estado_operadora,
            movimiento_desde=movimiento_desde,
            movimiento_hasta=movimiento_hasta,
            mes=mes,
        ))

