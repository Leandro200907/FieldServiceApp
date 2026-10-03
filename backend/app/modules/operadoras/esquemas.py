"""Validación de filas de planilla alineada con el comando JSON de registro."""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.api.errores import ErrorDeDominio


class CamposPlanillaOperadora(BaseModel):
    operadora: str = Field(min_length=1, max_length=200)
    observacion: str | None = Field(None, max_length=2000)

    @field_validator("operadora", mode="before")
    @classmethod
    def _operadora_sin_bordes(cls, valor: object) -> str:
        return str(valor or "").strip()

    @field_validator("observacion", mode="before")
    @classmethod
    def _observacion_opcional(cls, valor: object) -> str | None:
        if valor in (None, ""):
            return None
        return str(valor).strip()


def validar_campos_planilla(fila: dict) -> None:
    try:
        CamposPlanillaOperadora.model_validate({
            "operadora": fila.get("operadora"),
            "observacion": fila.get("observacion"),
        })
    except ValidationError as err:
        detalle = err.errors()[0]
        campo = ".".join(str(x) for x in detalle["loc"])
        if campo == "operadora" and detalle["type"] in {"string_too_short", "missing"}:
            mensaje = "Falta la operadora"
        else:
            mensaje = "Fila con formato inválido"
        raise ErrorDeDominio(
            mensaje,
            {"campo": campo, "tipo": detalle["type"], "mensaje": detalle["msg"]},
            codigo="fila_invalida",
        ) from err
