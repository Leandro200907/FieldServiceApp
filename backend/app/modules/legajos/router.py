"""POST /v1/comandos/* del dominio Evidencia. Permisos: matriz 2.2 del brief."""
from typing import Any

from fastapi import APIRouter, Depends

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.modules.legajos import esquemas as e
from app.modules.legajos import servicio
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando

router = APIRouter(tags=["legajos"])

RESPONSABLE = (Rol.RESPONSABLE_LEGAJOS,)
TECNICO = (Rol.TECNICO,)
CONFIG_O_RESPONSABLE = (Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)


def _ruta(nombre: str, body_cls: type, fn, roles: tuple[Rol, ...], clave_de_body=None) -> None:
    """`clave_de_body`: para comandos naturalmente idempotentes por un id del body
    (ImportarLote → `lote:<lote_id>`, regla 6 del brief) esa clave prevalece sobre el
    header Idempotency-Key."""

    def endpoint(
        body,
        identidad: Identidad = Depends(identidad_actual),
        clave: str | None = Depends(clave_idempotencia),
    ) -> dict[str, Any]:
        clave_efectiva = clave_de_body(body) if clave_de_body else clave
        # Un lote es idempotente por lote_id (8.2), pero el fingerprint incluye el hash
        # canónico del contenido: mismo lote con filas distintas es 409, no un replay.
        huella = body.model_dump(mode="json")
        return ejecutar_comando(
            identidad, clave_efectiva, roles, lambda s: fn(s, identidad, body),
            ruta=f"/comandos/{nombre}", body=huella,
        )

    # El tipo del body se fija en runtime (una función por comando, mismo patrón).
    endpoint.__annotations__["body"] = body_cls
    endpoint.__name__ = nombre
    router.post(f"/comandos/{nombre}", name=nombre)(endpoint)


_ruta("alta_de_sujeto", e.AltaDeSujeto, servicio.alta_de_sujeto, RESPONSABLE)
_ruta("baja_de_sujeto", e.BajaDeSujeto, servicio.baja_de_sujeto, RESPONSABLE)
_ruta("cargar_documento", e.CargarDocumento, servicio.cargar_documento, RESPONSABLE)
_ruta("proponer_documento", e.ProponerDocumento, servicio.proponer_documento, TECNICO)
_ruta("confirmar_documento", e.ConfirmarDocumento, servicio.confirmar_documento, RESPONSABLE)
_ruta("rechazar_propuesta", e.RechazarPropuesta, servicio.rechazar_propuesta, RESPONSABLE)
_ruta(
    "registrar_acreditacion_de_competencia",
    e.RegistrarAcreditacionDeCompetencia,
    servicio.registrar_acreditacion_de_competencia,
    RESPONSABLE,
)
_ruta("registrar_induccion", e.RegistrarInduccion, servicio.registrar_induccion, RESPONSABLE)
_ruta("importar_lote", e.ImportarLote, servicio.importar_lote, RESPONSABLE, clave_de_body=lambda b: f"lote:{b.lote_id}")
_ruta("revertir_lote", e.RevertirLote, servicio.revertir_lote, RESPONSABLE)
_ruta("asignar_supervisor", e.AsignarSupervisor, servicio.asignar_supervisor, CONFIG_O_RESPONSABLE)
_ruta("reasignar_supervisor", e.ReasignarSupervisor, servicio.reasignar_supervisor, CONFIG_O_RESPONSABLE)
