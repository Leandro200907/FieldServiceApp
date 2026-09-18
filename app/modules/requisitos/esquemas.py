"""Bodies de los comandos de Requisitos (definiciones, matriz, requisito particular).

Enums según los CHECKs de docs_schema_actual.sql.
"""
from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Categoria = Literal["documento", "competencia", "induccion"]
TipoSujeto = Literal["empresa", "persona", "vehiculo", "equipo"]
Clasificacion = Literal["bloqueante_duro", "excepcionable"]


class DarDeAltaDefinicionDeRequisito(BaseModel):
    nombre: str = Field(min_length=1)
    categoria: Categoria
    tipo_sujeto_aplicable: TipoSujeto
    locacion_id: UUID | None = None  # obligatoria si categoria=induccion, prohibida si no
    definicion_global_id: UUID | None = None
    plazo_retencion_archivo_dias: int | None = Field(default=None, ge=1)


class DarDeBajaDefinicionDeRequisito(BaseModel):
    requisito_definicion_id: UUID


class LineaDeMatriz(BaseModel):
    requisito_definicion_id: UUID
    clasificacion: Clasificacion
    bloqueante_durante_ejecucion: bool


class PublicarVersionDeMatriz(BaseModel):
    cliente_id: UUID
    locacion_id: UUID
    tipo_servicio_id: UUID
    vigente_desde: date
    lineas: list[LineaDeMatriz]
    fuente: str | None = None
    archivo_de_respaldo: str | None = None
    autor: str | None = None

    @field_validator("lineas")
    @classmethod
    def _lineas_validas(cls, v: list[LineaDeMatriz]) -> list[LineaDeMatriz]:
        if not v:
            raise ValueError("la matriz necesita al menos una línea")
        ids = [str(x.requisito_definicion_id) for x in v]
        if len(ids) != len(set(ids)):
            raise ValueError("hay requisitos repetidos en las líneas")
        return v


class CargarRequisitoParticular(BaseModel):
    commitment_id: str = Field(min_length=1)
    requisito_definicion_id: UUID
    clasificacion: Clasificacion
    bloqueante_durante_ejecucion: bool
