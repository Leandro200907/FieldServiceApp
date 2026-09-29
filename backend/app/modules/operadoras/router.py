from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import hashlib

from fastapi import APIRouter, Body, Depends, Header, Query
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


class ResultadoFilaImportada(BaseModel):
    fila: int
    documento_id: str
    operadora_id: str
    estado: str


class ErrorFilaImportada(BaseModel):
    fila: int
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
    contenido: bytes = Body(media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", max_length=5 * 1024 * 1024),
    nombre_archivo: str = Header("presentaciones_operadoras.xlsx", alias="X-Nombre-Archivo", max_length=500),
    hoja: str = Query("Presentaciones", min_length=1, max_length=200),
) -> ImportarPlanillaOperadorasResponse:
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
        lambda s: servicio.importar_filas(s, identidad, archivo=nombre_archivo, hoja=hoja, filas=filas),
        ruta="/comandos/importar_planilla_operadoras",
        body={"archivo": nombre_archivo, "hoja": hoja, "sha256": huella},
    )
    return ImportarPlanillaOperadorasResponse(**resultado)


@router.get("/consultas/alertas_actualizacion_operadora", response_model=AlertasOperadoraResponse)
def alertas_actualizacion_operadora(
    sujeto_id: str | None = Query(None),
    estado: Literal["pendiente_envio", "pendiente_aceptacion", "rechazado"] | None = Query(None),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> AlertasOperadoraResponse:
    with tenant_session(identidad.tenant_id) as session:
        return AlertasOperadoraResponse(**servicio.alertas(session, identidad, p, sujeto_id=sujeto_id, estado=estado))

