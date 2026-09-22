"""POST /v1/comandos/* del dominio Requisitos. Permisos: matriz 2.2 del brief."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando
from app.modules.requisitos import esquemas as e
from app.modules.requisitos import plantillas, servicio

router = APIRouter(tags=["requisitos"])

CONFIGURACION = (Rol.CONFIGURACION,)
RESPONSABLE = (Rol.RESPONSABLE_LEGAJOS,)


# --------------------------------------------------------------------------- respuestas


class DarDeAltaDefinicionDeRequisitoResponse(BaseModel):
    requisito_definicion_id: str
    eventos: list[str]


class DarDeBajaDefinicionDeRequisitoResponse(BaseModel):
    requisito_definicion_id: str
    eventos: list[str]


class VersionAnteriorDeMatriz(BaseModel):
    matriz_version_id: str
    version: int
    vigente_hasta: date | None


class PublicarVersionDeMatrizResponse(BaseModel):
    matriz_version_id: str
    version: int
    vigente_desde: date
    version_anterior: VersionAnteriorDeMatriz | None
    eventos: list[str]


class CargarRequisitoParticularResponse(BaseModel):
    requisito_particular_id: str
    eventos: list[str]


class CopiarDefinicionGlobalResponse(BaseModel):
    requisito_definicion_id: str
    definicion_global_id: str
    copiada_de_version: int
    eventos: list[str]


class CopiarMatrizGlobalResponse(BaseModel):
    matriz_version_id: str
    version: int
    vigente_desde: date
    version_anterior: VersionAnteriorDeMatriz | None
    matriz_global_id: str
    copiada_de_version: int
    definiciones_creadas: list[str]
    eventos: list[str]


def _ruta(nombre: str, body_cls: type, fn, roles: tuple[Rol, ...], response_model_cls: type) -> None:
    def endpoint(
        body,
        identidad: Identidad = Depends(identidad_actual),
        clave: str | None = Depends(clave_idempotencia),
    ) -> response_model_cls:  # type: ignore[valid-type]
        resultado = ejecutar_comando(
            identidad, clave, roles, lambda s: fn(s, identidad, body),
            ruta=f"/comandos/{nombre}", body=body.model_dump(mode="json"),
        )
        return response_model_cls(**resultado)

    endpoint.__annotations__["body"] = body_cls
    endpoint.__annotations__["return"] = response_model_cls
    endpoint.__name__ = nombre
    router.post(f"/comandos/{nombre}", name=nombre, response_model=response_model_cls)(endpoint)


_ruta(
    "dar_de_alta_definicion_de_requisito",
    e.DarDeAltaDefinicionDeRequisito,
    servicio.dar_de_alta_definicion_de_requisito,
    CONFIGURACION,
    DarDeAltaDefinicionDeRequisitoResponse,
)
_ruta(
    "dar_de_baja_definicion_de_requisito",
    e.DarDeBajaDefinicionDeRequisito,
    servicio.dar_de_baja_definicion_de_requisito,
    CONFIGURACION,
    DarDeBajaDefinicionDeRequisitoResponse,
)
_ruta(
    "publicar_version_de_matriz",
    e.PublicarVersionDeMatriz,
    servicio.publicar_version_de_matriz,
    CONFIGURACION,
    PublicarVersionDeMatrizResponse,
)
_ruta(
    "cargar_requisito_particular",
    e.CargarRequisitoParticular,
    servicio.cargar_requisito_particular,
    RESPONSABLE,
    CargarRequisitoParticularResponse,
)
_ruta(
    "copiar_definicion_global",
    e.CopiarDefinicionGlobal,
    plantillas.copiar_definicion_global,
    CONFIGURACION,
    CopiarDefinicionGlobalResponse,
)
_ruta(
    "copiar_matriz_global",
    e.CopiarMatrizGlobal,
    plantillas.copiar_matriz_global,
    CONFIGURACION,
    CopiarMatrizGlobalResponse,
)
