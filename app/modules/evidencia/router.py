"""Validación técnica de evidencia (reauditoría Fase 2 punto 2): comando manual de
invalidación (Responsable_legajos) y bandeja de seguimiento."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.evidencia import servicio
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando

router = APIRouter(tags=["evidencia"])


class InvalidarEvidenciaBody(BaseModel):
    documento_id: str = Field(min_length=1)
    motivo: str = Field(min_length=1)


@router.post("/comandos/invalidar_evidencia")
def invalidar_evidencia(
    body: InvalidarEvidenciaBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)
) -> dict[str, Any]:
    return ejecutar_comando(
        identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
        lambda s: servicio.invalidar_evidencia_verificada(s, identidad, **body.model_dump()),
        ruta="/comandos/invalidar_evidencia", body=body.model_dump(mode="json"),
    )


@router.get("/consultas/bandeja_validacion_evidencia")
def bandeja_validacion_evidencia(
    estado: Literal["accion_requerida", "pendiente", "valido", "invalido", "todos"] | None = Query(None),
    identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina),
) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return servicio.bandeja(s, identidad, p, estado)
