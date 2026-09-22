"""POST /v1/comandos/* de Operación (custodia, excepciones, constancias, evaluación).

El router solo hace transporte: valida el body (pydantic), toma la identidad del JWT,
abre UNA `tenant_session` por request, resuelve `Idempotency-Key` y delega en
`servicio`. Los permisos y las reglas de dominio viven en el servicio.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad
from app.comun.idempotencia import ejecutar_idempotente, fingerprint_de
from app.db import tenant_session
from app.modules.operacion import servicio

router = APIRouter(prefix="/comandos", tags=["operacion"])


def _ejecutar(
    identidad: Identidad, clave: str | None, comando: Callable[[Session], dict[str, Any]], *, ruta: str, body: Any,
    prevalidar: Callable[[Session], None] | None = None,
) -> dict[str, Any]:
    """Idempotencia con reserva atómica (A-03): ver app/comun/idempotencia.py. `prevalidar`
    (alcance actual del recurso) corre siempre, también antes de un replay."""
    return ejecutar_idempotente(
        identidad.tenant_id, identidad.usuario_id, clave, fingerprint_de("POST", ruta, body.model_dump(mode="json")),
        comando, prevalidar=prevalidar,
    )


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
    """`origen_sujetos` NO es parte del contrato público: lo determina exclusivamente el
    servidor (este endpoint siempre produce 'explicito'). Enviarlo es un error 422."""

    model_config = ConfigDict(extra="forbid")

    commitment_id: str = Field(min_length=1)
    sujetos_propuestos: list[str] = Field(min_length=1, max_length=200)


# --------------------------------------------------------------------------- responses


class CambiarCustodiaResponse(BaseModel):
    custodia_id: str
    periodo_id: str
    periodo_cerrado_id: str | None = None
    eventos: list[str]


class CorregirCustodiaResponse(BaseModel):
    custodia_id: str
    periodo_id: str
    periodo_corregido_id: str
    eventos: list[str]


class OtorgarExcepcionResponse(BaseModel):
    excepcion_id: str
    eventos: list[str]


class RevocarExcepcionResponse(BaseModel):
    excepcion_id: str
    eventos: list[str]


class RegistrarConstanciaResponse(BaseModel):
    constancia_id: str
    constancia_reemplazada_id: str | None = None
    eventos: list[str]


class RevocarConstanciaResponse(BaseModel):
    constancia_id: str
    eventos: list[str]


class RequisitoEvaluado(BaseModel):
    """Pieza atómica de `por_sujeto[].requisitos[]` — un (sujeto, requisito) puntual
    (ver app/core/tipos.py:VeredictoRequisito y app/core/orquestacion.py:_evaluar_requisito)."""

    requisito_definicion_id: str
    veredicto: str
    motivo: str | None = None
    nombre: str | None = None
    categoria: str | None = None
    clasificacion: str
    origen_clasificacion: str
    bloqueante_durante_ejecucion: bool
    documento_id: str | None = None
    constancia_id: str | None = None
    excepcion_id: str | None = None
    bajo_excepcion: bool = False
    asignable: bool = False
    excepcion_aplicable_pero_sin_efecto: bool = False
    anulacion_detectada: str | None = None


class SujetoEvaluado(BaseModel):
    sujeto_id: str
    tipo_sujeto: str
    veredicto: str
    asignable: bool
    bajo_excepcion: bool
    requisitos: list[RequisitoEvaluado]
    representante: bool


class RequisitoFaltante(BaseModel):
    tipo_sujeto: str
    sujeto_id: str | None = None
    requisito_definicion_id: str | None = None
    veredicto: str
    motivo: str
    bajo_excepcion: bool
    nombre: str | None = None


class VersionMatriz(BaseModel):
    matriz_version_id: str
    version: int


class EvaluarHabilitacionResponse(BaseModel):
    referencia_evaluacion: str
    commitment_id: str
    modo: str
    sujetos_propuestos: list[str]
    origen_sujetos: str
    avisos_cerrados: list[str]
    veredicto_de_cumplimiento: str
    resultado_de_decision: str
    por_sujeto: list[SujetoEvaluado]
    requisitos_faltantes: list[RequisitoFaltante]
    version_matriz: VersionMatriz
    # `snapshot` es el dump de auditoría persistido tal cual en la columna jsonb (incluye
    # filas crudas de OC/matriz/línea y metadata de cálculo): no es un contrato de API
    # fijo, así que se documenta como objeto libre en vez de fijar cada clave.
    snapshot: dict[str, Any]
    creado_en: str
    eventos: list[str]


# --------------------------------------------------------------------------- endpoints


@router.post("/cambiar_custodia", response_model=CambiarCustodiaResponse)
def cambiar_custodia(
    body: CambiarCustodiaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CambiarCustodiaResponse:
    resultado = _ejecutar(identidad, idempotency_key, lambda s: servicio.cambiar_custodia(s, identidad, **body.model_dump()), ruta="/comandos/cambiar_custodia", body=body)
    return CambiarCustodiaResponse(**resultado)


@router.post("/corregir_custodia", response_model=CorregirCustodiaResponse)
def corregir_custodia(
    body: CorregirCustodiaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CorregirCustodiaResponse:
    resultado = _ejecutar(identidad, idempotency_key, lambda s: servicio.corregir_custodia(s, identidad, **body.model_dump()), ruta="/comandos/corregir_custodia", body=body)
    return CorregirCustodiaResponse(**resultado)


@router.post("/otorgar_excepcion", response_model=OtorgarExcepcionResponse)
def otorgar_excepcion(
    body: OtorgarExcepcionBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> OtorgarExcepcionResponse:
    resultado = _ejecutar(
        identidad, idempotency_key, lambda s: servicio.otorgar_excepcion(s, identidad, **body.model_dump()),
        ruta="/comandos/otorgar_excepcion", body=body,
        prevalidar=lambda s: servicio.prevalidar_otorgar_excepcion(s, identidad, **body.model_dump()),
    )
    return OtorgarExcepcionResponse(**resultado)


@router.post("/revocar_excepcion", response_model=RevocarExcepcionResponse)
def revocar_excepcion(
    body: RevocarExcepcionBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RevocarExcepcionResponse:
    resultado = _ejecutar(
        identidad, idempotency_key, lambda s: servicio.revocar_excepcion(s, identidad, **body.model_dump()),
        ruta="/comandos/revocar_excepcion", body=body,
        prevalidar=lambda s: servicio.prevalidar_revocar_excepcion(s, identidad, **body.model_dump()),
    )
    return RevocarExcepcionResponse(**resultado)


@router.post("/registrar_constancia_del_cliente", response_model=RegistrarConstanciaResponse)
def registrar_constancia_del_cliente(
    body: RegistrarConstanciaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RegistrarConstanciaResponse:
    resultado = _ejecutar(
        identidad, idempotency_key, lambda s: servicio.registrar_constancia_del_cliente(s, identidad, **body.model_dump()),
        ruta="/comandos/registrar_constancia_del_cliente", body=body,
    )
    return RegistrarConstanciaResponse(**resultado)


@router.post("/revocar_constancia_del_cliente", response_model=RevocarConstanciaResponse)
def revocar_constancia_del_cliente(
    body: RevocarConstanciaBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RevocarConstanciaResponse:
    resultado = _ejecutar(
        identidad, idempotency_key, lambda s: servicio.revocar_constancia_del_cliente(s, identidad, **body.model_dump()),
        ruta="/comandos/revocar_constancia_del_cliente", body=body,
    )
    return RevocarConstanciaResponse(**resultado)


@router.post("/evaluar_habilitacion", response_model=EvaluarHabilitacionResponse)
def evaluar_habilitacion(
    body: EvaluarHabilitacionBody,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> EvaluarHabilitacionResponse:
    resultado = _ejecutar(identidad, idempotency_key, lambda s: servicio.evaluar_habilitacion(s, identidad, **body.model_dump()), ruta="/comandos/evaluar_habilitacion", body=body)
    return EvaluarHabilitacionResponse(**resultado)
