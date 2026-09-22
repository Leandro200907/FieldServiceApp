"""POST /v1/comandos/* del dominio Evidencia. Permisos: matriz 2.2 del brief."""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.modules.legajos import esquemas as e
from app.modules.legajos import servicio
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando

router = APIRouter(tags=["legajos"])

RESPONSABLE = (Rol.RESPONSABLE_LEGAJOS,)
TECNICO = (Rol.TECNICO,)
CONFIG_O_RESPONSABLE = (Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)


# --------------------------------------------------------------------------- response models


class LegajoResponse(BaseModel):
    """alta_de_sujeto / baja_de_sujeto."""

    legajo_id: str
    sujeto_id: str
    eventos: list[str]


class DocumentoCargadoResponse(BaseModel):
    """cargar_documento / proponer_documento (comparten el núcleo `_insertar_version_documento`)."""

    documento_id: str
    version: int
    sucede_a: str | None
    eventos: list[str]


class ConfirmarDocumentoResponse(BaseModel):
    documento_id: str
    excepciones_regularizadas: list[str]
    eventos: list[str]


class RechazarPropuestaResponse(BaseModel):
    documento_id: str
    restaurado_documento_id: str | None
    eventos: list[str]


class RegistrarAcreditacionDeCompetenciaResponse(BaseModel):
    acreditacion_id: str
    eventos: list[str]


class RegistrarInduccionResponse(BaseModel):
    induccion_id: str
    eventos: list[str]


class FilaRechazadaLote(BaseModel):
    fila: int
    sujeto_id: str | None
    requisito_definicion_id: str | None
    codigo: str
    motivo: str
    # Heterogéneo a propósito: `fila_invalida` trae una lista de errores por campo
    # ({"campo", "tipo", "mensaje"}); un ErrorDeDominio trae `detalles` (dict) o None.
    detalles: Any = None


class DocumentoDeLote(BaseModel):
    fila: int
    documento_id: str
    version: int
    sucede_a: str | None


class FilaSinCambiosDeLote(BaseModel):
    fila: int
    sujeto_id: str
    requisito_definicion_id: str
    documento_id: str


class ImportarLoteResponse(BaseModel):
    lote_id: str
    estado: str
    filas_totales: int
    filas_aceptadas: int
    filas_rechazadas: int
    detalle_filas_rechazadas: list[FilaRechazadaLote]
    documentos: list[DocumentoDeLote] = Field(default_factory=list)
    eventos: list[str]
    # Sólo presente en el replay de un lote ya aplicado (idempotencia por `lote_id`, 8.2).
    ya_aplicado: bool = False
    # Sólo presente cuando el lote se aplica de nuevo (no en el replay).
    filas_sin_cambios: list[FilaSinCambiosDeLote] | None = None


class RevertirLoteResponse(BaseModel):
    lote_id: str
    documentos_revertidos: list[str]
    documentos_restaurados: list[str]
    eventos: list[str]


class AsignarSupervisorResponse(BaseModel):
    asignacion_id: str
    sujeto_id: str
    desde: date
    eventos: list[str]


class ReasignarSupervisorResponse(BaseModel):
    asignacion_id: str
    asignacion_cerrada_id: str
    sujeto_id: str
    desde: date
    hasta_anterior: date
    eventos: list[str]


def _ruta(nombre: str, body_cls: type, fn, roles: tuple[Rol, ...], response_model_cls: type, clave_de_body=None) -> None:
    """`clave_de_body`: para comandos naturalmente idempotentes por un id del body
    (ImportarLote → `lote:<lote_id>`, regla 6 del brief) esa clave prevalece sobre el
    header Idempotency-Key."""

    def endpoint(
        body,
        identidad: Identidad = Depends(identidad_actual),
        clave: str | None = Depends(clave_idempotencia),
    ):
        clave_efectiva = clave_de_body(body) if clave_de_body else clave
        # Un lote es idempotente por lote_id (8.2), pero el fingerprint incluye el hash
        # canónico del contenido: mismo lote con filas distintas es 409, no un replay.
        huella = body.model_dump(mode="json")
        resultado = ejecutar_comando(
            identidad, clave_efectiva, roles, lambda s: fn(s, identidad, body),
            ruta=f"/comandos/{nombre}", body=huella,
        )
        return response_model_cls(**resultado)

    # El tipo del body se fija en runtime (una función por comando, mismo patrón).
    endpoint.__annotations__["body"] = body_cls
    endpoint.__annotations__["return"] = response_model_cls
    endpoint.__name__ = nombre
    router.post(f"/comandos/{nombre}", name=nombre, response_model=response_model_cls)(endpoint)


_ruta("alta_de_sujeto", e.AltaDeSujeto, servicio.alta_de_sujeto, RESPONSABLE, LegajoResponse)
_ruta("baja_de_sujeto", e.BajaDeSujeto, servicio.baja_de_sujeto, RESPONSABLE, LegajoResponse)
_ruta("cargar_documento", e.CargarDocumento, servicio.cargar_documento, RESPONSABLE, DocumentoCargadoResponse)
_ruta("proponer_documento", e.ProponerDocumento, servicio.proponer_documento, TECNICO, DocumentoCargadoResponse)
_ruta("confirmar_documento", e.ConfirmarDocumento, servicio.confirmar_documento, RESPONSABLE, ConfirmarDocumentoResponse)
_ruta("rechazar_propuesta", e.RechazarPropuesta, servicio.rechazar_propuesta, RESPONSABLE, RechazarPropuestaResponse)
_ruta(
    "registrar_acreditacion_de_competencia",
    e.RegistrarAcreditacionDeCompetencia,
    servicio.registrar_acreditacion_de_competencia,
    RESPONSABLE,
    RegistrarAcreditacionDeCompetenciaResponse,
)
_ruta("registrar_induccion", e.RegistrarInduccion, servicio.registrar_induccion, RESPONSABLE, RegistrarInduccionResponse)
_ruta(
    "importar_lote", e.ImportarLote, servicio.importar_lote, RESPONSABLE, ImportarLoteResponse,
    clave_de_body=lambda b: f"lote:{b.lote_id}",
)
_ruta("revertir_lote", e.RevertirLote, servicio.revertir_lote, RESPONSABLE, RevertirLoteResponse)
_ruta("asignar_supervisor", e.AsignarSupervisor, servicio.asignar_supervisor, CONFIG_O_RESPONSABLE, AsignarSupervisorResponse)
_ruta(
    "reasignar_supervisor", e.ReasignarSupervisor, servicio.reasignar_supervisor, CONFIG_O_RESPONSABLE,
    ReasignarSupervisorResponse,
)
