"""Bodies de los comandos de Evidencia (legajos, documentos, lotes, supervisores).

Los enums vienen de docs_schema_actual.sql (CHECKs de cada tabla), no se inventan.
"""
from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

TipoSujeto = Literal["empresa", "persona", "vehiculo", "equipo"]
OrigenDocumento = Literal["planilla", "carga_manual", "drive"]
OrigenLote = Literal["planilla", "drive"]
EstadoConfirmacion = Literal["declarado", "verificado", "confirmado_en_fuente"]
Confianza = Literal["alta", "media", "baja"]


class AltaDeSujeto(BaseModel):
    tipo_sujeto: TipoSujeto
    identificador_natural: str = Field(min_length=1)
    sujeto_id: str | None = Field(default=None, min_length=1)


class BajaDeSujeto(BaseModel):
    sujeto_id: str = Field(min_length=1)


class CargarDocumento(BaseModel):
    sujeto_id: str = Field(min_length=1)
    requisito_definicion_id: UUID
    vigente_desde: date
    vigente_hasta: date
    numero: str | None = None
    origen: OrigenDocumento = "carga_manual"
    # Cuando lo carga el responsable, por defecto ya lo está verificando (1.10).
    estado_confirmacion: EstadoConfirmacion = "verificado"
    confianza_extraccion: Confianza | None = None
    clave_storage: str | None = None
    checksum_archivo: str | None = None


class ProponerDocumento(BaseModel):
    sujeto_id: str = Field(min_length=1)
    requisito_definicion_id: UUID
    vigente_desde: date
    vigente_hasta: date
    numero: str | None = None
    origen: OrigenDocumento = "carga_manual"
    clave_storage: str | None = None
    checksum_archivo: str | None = None


class ConfirmarDocumento(BaseModel):
    documento_id: UUID


class RechazarPropuesta(BaseModel):
    documento_id: UUID
    motivo: str | None = None


class RegistrarAcreditacionDeCompetencia(BaseModel):
    persona_id: str = Field(min_length=1)
    requisito_definicion_id: UUID
    vigente_desde: date
    vigente_hasta: date
    evidencias: list[UUID] = Field(min_length=1)
    estado_confirmacion: EstadoConfirmacion = "verificado"


class RegistrarInduccion(BaseModel):
    persona_id: str = Field(min_length=1)
    locacion_id: UUID
    requisito_definicion_id: UUID
    vigente_desde: date
    vigente_hasta: date
    evidencia: UUID
    estado_confirmacion: EstadoConfirmacion = "verificado"


class FilaDeLote(BaseModel):
    sujeto_id: str = Field(min_length=1)
    requisito_definicion_id: UUID
    vigente_desde: date
    vigente_hasta: date
    numero: str | None = None
    # Lo importado en masa nace declarado: nadie lo miró todavía (1.10).
    estado_confirmacion: EstadoConfirmacion = "declarado"


class ImportarLote(BaseModel):
    lote_id: UUID
    origen: OrigenLote = "planilla"
    filas: list[FilaDeLote] = Field(default_factory=list)
    hash_archivo: str | None = None

    @field_validator("filas")
    @classmethod
    def _no_vacio(cls, v: list[FilaDeLote]) -> list[FilaDeLote]:
        if not v:
            raise ValueError("el lote no tiene filas")
        return v


class RevertirLote(BaseModel):
    lote_id: UUID


class AsignarSupervisor(BaseModel):
    sujeto_id: str = Field(min_length=1)
    supervisor_usuario_id: UUID
    desde: date | None = None  # default: hoy del tenant


class ReasignarSupervisor(AsignarSupervisor):
    pass
