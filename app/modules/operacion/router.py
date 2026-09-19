"""POST /v1/comandos/* de Operación (custodia, excepciones, constancias, evaluación).

El router solo hace transporte: valida el body (pydantic), toma la identidad del JWT,
abre UNA `tenant_session` por request, resuelve `Idempotency-Key` y delega en
`servicio`. Los permisos y las reglas de dominio viven en el servicio.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad
from app.comun.idempotencia import buscar_resultado, guardar_resultado
from app.db import tenant_session
from app.modules.operacion import servicio

router = APIRouter(prefix="/comandos", tags=["operacion"])


def _ejecutar(identidad: Identidad, clave: str | None, comando: Callable[[Session], dict[str, Any]]) -> dict[str, Any]:
    with tenant_session(identidad.tenant_id) as s:
        previo = buscar_resultado(s, identidad.tenant_id, clave)
        if previo is not None:
            return previo
        resultado = comando(s)
        guardar_resultado(s, identidad.tenant_id, clave, resultado)
        return resultado


# --------------------------------------------------------------------------- bodies


class CambiarCustodiaBody(BaseModel):
    recurso_id: str = Field(min_length=1)
    tipo_recurso: str = Field(pattern="^(vehiculo|equipo)$")
    custodio_id: str | None = None
    desde: date


class CorregirCustodiaBody(BaseModel):
    periodo_id: str
    custodio_id: str | None = None
    desde: date | None = None
    hasta: date | None = None
    motivo: str | None = None


class OtorgarExcepcionBody(BaseModel):
    referencia_evaluacion: str
    sujeto_id: str = Field(min_length=1)
    requisito_definicion_id: str
    commitment_id: str = Field(min_length=1)
    motivo: str = Field(min_length=1)
    vigencia: date | None = None
    evidencia: str | None = None


class RevocarExcepcionBody(BaseModel):
    excepcion_id: str
    motivo: str | None = None


class RegistrarConstanciaBody(BaseModel):
    sujeto_id: str = Field(min_length=1)
    requisito_definicion_id: str
    cliente_id: str
    evidencia: str = Field(min_length=1)
    commitment_id: str | None = None
    emisor: str | None = None
    vigencia: date | None = None


class RevocarConstanciaBody(BaseModel):
    constancia_id: str
    motivo: str | None = None


class EvaluarHabilitacionBody(BaseModel):
    commitment_id: str = Field(min_length=1)
    sujetos_propuestos: list[str] = Field(min_length=1, max_length=200)


# --------------------------------------------------------------------------- endpoints


@router.post("/cambiar_custodia")
def cambiar_custodia(
    body: CambiarCustodiaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _ejecutar(identidad, idempotency_key, lambda s: servicio.cambiar_custodia(s, identidad, **body.model_dump()))


@router.post("/corregir_custodia")
def corregir_custodia(
    body: CorregirCustodiaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _ejecutar(identidad, idempotency_key, lambda s: servicio.corregir_custodia(s, identidad, **body.model_dump()))


@router.post("/otorgar_excepcion")
def otorgar_excepcion(
    body: OtorgarExcepcionBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _ejecutar(identidad, idempotency_key, lambda s: servicio.otorgar_excepcion(s, identidad, **body.model_dump()))


@router.post("/revocar_excepcion")
def revocar_excepcion(
    body: RevocarExcepcionBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _ejecutar(identidad, idempotency_key, lambda s: servicio.revocar_excepcion(s, identidad, **body.model_dump()))


@router.post("/registrar_constancia_del_cliente")
def registrar_constancia_del_cliente(
    body: RegistrarConstanciaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _ejecutar(
        identidad, idempotency_key, lambda s: servicio.registrar_constancia_del_cliente(s, identidad, **body.model_dump())
    )


@router.post("/revocar_constancia_del_cliente")
def revocar_constancia_del_cliente(
    body: RevocarConstanciaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _ejecutar(
        identidad, idempotency_key, lambda s: servicio.revocar_constancia_del_cliente(s, identidad, **body.model_dump())
    )


@router.post("/evaluar_habilitacion")
def evaluar_habilitacion(
    body: EvaluarHabilitacionBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    return _ejecutar(identidad, idempotency_key, lambda s: servicio.evaluar_habilitacion(s, identidad, **body.model_dump()))
