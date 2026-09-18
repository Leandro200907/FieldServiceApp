"""POST /v1/comandos/* del dominio Requisitos. Permisos: matriz 2.2 del brief."""
from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando
from app.modules.requisitos import esquemas as e
from app.modules.requisitos import servicio

router = APIRouter(tags=["requisitos"])

CONFIGURACION = (Rol.CONFIGURACION,)
RESPONSABLE = (Rol.RESPONSABLE_LEGAJOS,)


def _ruta(nombre: str, body_cls: type, fn, roles: tuple[Rol, ...]) -> None:
    def endpoint(
        body,
        identidad: Identidad = Depends(identidad_actual),
        clave: str | None = Depends(clave_idempotencia),
    ) -> dict[str, Any]:
        return ejecutar_comando(identidad, clave, roles, lambda s: fn(s, identidad, body))

    endpoint.__annotations__["body"] = body_cls
    endpoint.__name__ = nombre
    router.post(f"/comandos/{nombre}", name=nombre)(endpoint)


_ruta(
    "dar_de_alta_definicion_de_requisito",
    e.DarDeAltaDefinicionDeRequisito,
    servicio.dar_de_alta_definicion_de_requisito,
    CONFIGURACION,
)
_ruta(
    "dar_de_baja_definicion_de_requisito",
    e.DarDeBajaDefinicionDeRequisito,
    servicio.dar_de_baja_definicion_de_requisito,
    CONFIGURACION,
)
_ruta("publicar_version_de_matriz", e.PublicarVersionDeMatriz, servicio.publicar_version_de_matriz, CONFIGURACION)
_ruta("cargar_requisito_particular", e.CargarRequisitoParticular, servicio.cargar_requisito_particular, RESPONSABLE)
