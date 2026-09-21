"""POST /v1/comandos/importar_lote_oc y /v1/comandos/cancelar_oc."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.auth.identidad import Identidad, Rol
from app.comun.idempotencia import ejecutar_idempotente, fingerprint_de
from app.db import tenant_session
from app.auth.dependencies import identidad_actual
from app.modules.oc import servicio

router = APIRouter()


class ImportarLoteOC(BaseModel):
    lote_id: UUID
    origen: str
    # Las filas entran crudas a propósito: la validación es por fila (servicio.validar_fila)
    # para que una fila mala se rechace sola y no tire el lote entero con un 422.
    filas: list[dict[str, Any]] = Field(default_factory=list)


class CancelarOC(BaseModel):
    oc_id: UUID | None = None
    clave_origen: str | None = None


@router.post("/comandos/importar_lote_oc")
def importar_lote_oc(body: ImportarLoteOC, identidad: Identidad = Depends(identidad_actual)) -> dict:
    # Idempotente por lote_id del body (regla dura 6); el header Idempotency-Key no aplica acá.
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    return ejecutar_idempotente(
        identidad.tenant_id, identidad.usuario_id, f"lote:{body.lote_id}",
        fingerprint_de("POST", "/comandos/importar_lote_oc", body.model_dump(mode="json")),
        lambda s: servicio.importar_lote_oc(s, identidad, str(body.lote_id), body.origen, body.filas),
    )


@router.post("/comandos/cancelar_oc")
def cancelar_oc(
    body: CancelarOC,
    identidad: Identidad = Depends(identidad_actual),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    return ejecutar_idempotente(
        identidad.tenant_id, identidad.usuario_id, idempotency_key,
        fingerprint_de("POST", "/comandos/cancelar_oc", body.model_dump(mode="json")),
        lambda s: servicio.cancelar_oc(s, identidad, str(body.oc_id) if body.oc_id else None, body.clave_origen),
    )
