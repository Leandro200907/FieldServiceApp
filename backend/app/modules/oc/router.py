"""POST /v1/comandos/importar_lote_oc y /v1/comandos/cancelar_oc."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field

from app.api.errores import ErrorDeDominio
from app.modules.oc.lector_planilla_oc import leer_planilla_oc

from app.auth.identidad import Identidad, Rol
from app.comun.idempotencia import ejecutar_idempotente, fingerprint_de
from app.db import tenant_session
from app.auth.dependencies import identidad_actual
from app.modules.oc import catalogos_maestros, servicio

router = APIRouter()


class CatalogosOcResponse(BaseModel):
    operadoras: list[dict[str, Any]]
    locaciones: list[dict[str, Any]]
    tipos_servicio: list[dict[str, Any]]


class AltaOperadoraBody(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)


class AltaLocacionBody(BaseModel):
    operadora_id: UUID
    nombre: str = Field(min_length=1, max_length=200)


class AltaTipoServicioBody(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)


class ImportarLoteOC(BaseModel):
    lote_id: UUID
    origen: str
    # Las filas entran crudas a propósito: la validación es por fila (servicio.validar_fila)
    # para que una fila mala se rechace sola y no tire el lote entero con un 422.
    filas: list[dict[str, Any]] = Field(default_factory=list)


class CancelarOC(BaseModel):
    oc_id: UUID | None = None
    clave_origen: str | None = None


class ReprogramarOcBody(BaseModel):
    oc_id: UUID
    vigencia_desde: date
    vigencia_hasta: date
    motivo: str = Field(min_length=1, max_length=500)


class FilaRechazada(BaseModel):
    indice: int
    clave_origen: str | None
    motivo: str


class OcModificada(BaseModel):
    commitment_id: str
    campos_modificados: list[str]
    evento_id: str


class ImportarLoteOCResponse(BaseModel):
    lote_id: str
    estado: str
    filas_totales: int
    filas_aceptadas: int
    filas_rechazadas: int
    detalle_filas_rechazadas: list[FilaRechazada]
    oc_ids: list[str]
    ya_aplicado: bool
    eventos: list[str]
    # Sólo presentes cuando `ya_aplicado` es False (lote recién aplicado, no un replay).
    oc_creadas: int | None = None
    oc_actualizadas: int | None = None
    oc_modificadas: list[OcModificada] | None = None


class CancelarOCResponse(BaseModel):
    oc_id: str
    clave_origen: str
    estado: str
    eventos: list[str]


class ImportarPlanillaOcResponse(ImportarLoteOCResponse):
    errores_lectura: list[str] = Field(default_factory=list)


@router.get("/consultas/catalogos_oc", response_model=CatalogosOcResponse)
def catalogos_oc(identidad: Identidad = Depends(identidad_actual)) -> CatalogosOcResponse:
    with tenant_session(identidad.tenant_id) as s:
        return CatalogosOcResponse(**catalogos_maestros.listar_catalogos(s, identidad))


@router.post("/comandos/alta_operadora_oc")
def alta_operadora_oc(body: AltaOperadoraBody, identidad: Identidad = Depends(identidad_actual)) -> dict[str, Any]:
    with tenant_session(identidad.tenant_id) as s:
        return catalogos_maestros.alta_operadora(s, identidad, body.nombre)


@router.post("/comandos/alta_locacion_oc")
def alta_locacion_oc(body: AltaLocacionBody, identidad: Identidad = Depends(identidad_actual)) -> dict[str, Any]:
    with tenant_session(identidad.tenant_id) as s:
        return catalogos_maestros.alta_locacion(s, identidad, str(body.operadora_id), body.nombre)


@router.post("/comandos/alta_tipo_servicio_oc")
def alta_tipo_servicio_oc(body: AltaTipoServicioBody, identidad: Identidad = Depends(identidad_actual)) -> dict[str, Any]:
    with tenant_session(identidad.tenant_id) as s:
        return catalogos_maestros.alta_tipo_servicio(s, identidad, body.nombre)


@router.post("/comandos/importar_planilla_oc", response_model=ImportarPlanillaOcResponse)
async def importar_planilla_oc(
    request: Request,
    identidad: Identidad = Depends(identidad_actual),
    lote_id: UUID = Query(...),
    hoja: str = Query("OC", max_length=80),
    nombre_archivo: str = Header("planilla_oc.xlsx", alias="X-Nombre-Archivo", max_length=500),
) -> ImportarPlanillaOcResponse:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    if not nombre_archivo.lower().endswith(".xlsx"):
        raise ErrorDeDominio("Solo se admite extensión .xlsx", {"nombre": nombre_archivo})
    media = request.headers.get("content-type", "")
    if "spreadsheet" not in media and media != "application/octet-stream":
        raise ErrorDeDominio("Content-Type debe ser XLSX", {"content_type": media})
    contenido = await request.body()
    if len(contenido) > 5 * 1024 * 1024:
        raise ErrorDeDominio("Archivo demasiado grande (máx. 5 MiB)")
    filas, errores_lectura = leer_planilla_oc(contenido, hoja=hoja)
    if errores_lectura and not filas:
        return ImportarPlanillaOcResponse(
            lote_id=str(lote_id), estado="rechazado", filas_totales=0, filas_aceptadas=0, filas_rechazadas=0,
            detalle_filas_rechazadas=[], oc_ids=[], ya_aplicado=False, eventos=[], errores_lectura=errores_lectura,
        )
    resultado = ejecutar_idempotente(
        identidad.tenant_id, identidad.usuario_id, f"lote_oc:{lote_id}",
        fingerprint_de("POST", "/comandos/importar_planilla_oc", {"lote_id": str(lote_id), "hoja": hoja, "filas": len(filas)}),
        lambda s: servicio.importar_lote_oc(s, identidad, str(lote_id), "planilla", filas),
    )
    return ImportarPlanillaOcResponse(**resultado, errores_lectura=errores_lectura)


@router.post("/comandos/importar_lote_oc", response_model=ImportarLoteOCResponse)
def importar_lote_oc(body: ImportarLoteOC, identidad: Identidad = Depends(identidad_actual)) -> ImportarLoteOCResponse:
    # Idempotente por lote_id del body (regla dura 6); el header Idempotency-Key no aplica acá.
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    resultado = ejecutar_idempotente(
        identidad.tenant_id, identidad.usuario_id, f"lote_oc:{body.lote_id}",
        fingerprint_de("POST", "/comandos/importar_lote_oc", body.model_dump(mode="json")),
        lambda s: servicio.importar_lote_oc(s, identidad, str(body.lote_id), body.origen, body.filas),
    )
    return ImportarLoteOCResponse(**resultado)


@router.post("/comandos/reprogramar_oc")
def reprogramar_oc(
    body: ReprogramarOcBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    resultado = ejecutar_idempotente(
        identidad.tenant_id,
        identidad.usuario_id,
        idempotency_key,
        fingerprint_de("POST", "/comandos/reprogramar_oc", body.model_dump(mode="json")),
        lambda s: servicio.reprogramar_oc(
            s, identidad, str(body.oc_id), body.vigencia_desde, body.vigencia_hasta, body.motivo,
        ),
    )
    return resultado


@router.post("/comandos/cancelar_oc", response_model=CancelarOCResponse)
def cancelar_oc(
    body: CancelarOC,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CancelarOCResponse:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    resultado = ejecutar_idempotente(
        identidad.tenant_id, identidad.usuario_id, idempotency_key,
        fingerprint_de("POST", "/comandos/cancelar_oc", body.model_dump(mode="json")),
        lambda s: servicio.cancelar_oc(s, identidad, str(body.oc_id) if body.oc_id else None, body.clave_origen),
    )
    return CancelarOCResponse(**resultado)
