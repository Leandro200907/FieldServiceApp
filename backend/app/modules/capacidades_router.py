"""Rutas de las capacidades v1 (H-01): canales de notificación, score documental,
exportación de legajo y Drive. Los comandos pasan por `ejecutar_comando` (rol +
idempotencia); las consultas abren `tenant_session` con la identidad del token."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.drive import servicio as drive
from app.modules.exportacion import servicio as exportacion
from app.modules.legajos.infra import clave_idempotencia, ejecutar_comando
from app.modules.notificaciones import servicio as notificaciones
from app.modules.score import servicio as score

router = APIRouter(tags=["capacidades"])


def _proveedor_drive():
    from app.modules.drive.proveedor import proveedor_de_plataforma
    return proveedor_de_plataforma()


def _storage():
    from app.storage import obtener_storage
    return obtener_storage()


# --------------------------------------------------------------------------- notificaciones


class ConfigurarCanalesBody(BaseModel):
    mail_habilitado: bool = False
    telegram_habilitado: bool = False
    remitente_nombre: str | None = Field(None, max_length=120)


class VincularTelegramBody(BaseModel):
    usuario_id: str
    chat_id: str | None = Field(None, max_length=32)


@router.post("/comandos/configurar_canales")
def configurar_canales(body: ConfigurarCanalesBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: notificaciones.configurar_canales(s, identidad, **body.model_dump()),
                            ruta="/comandos/configurar_canales", body=body.model_dump(mode="json"))


@router.post("/comandos/vincular_telegram")
def vincular_telegram(body: VincularTelegramBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: notificaciones.vincular_telegram(s, identidad, **body.model_dump()),
                            ruta="/comandos/vincular_telegram", body=body.model_dump(mode="json"))


@router.get("/consultas/configuracion_canales")
def configuracion_canales(identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return notificaciones.configuracion_canales(s, identidad)


@router.get("/consultas/envios_notificacion")
def envios_notificacion(
    estado: Literal["accion_requerida", "enviado", "fallido", "sin_canal", "registrado_log", "todos"] | None = Query(None),
    job_id: int | None = Query(None),
    identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina),
) -> dict:
    """Trazabilidad de entregas para seguimiento operativo. Por defecto (`estado` sin
    pasar, o `accion_requerida`): sólo `sin_canal` / `fallido` — lo que necesita que
    alguien haga algo. `registrado_log` nunca se cuenta como entrega real; se ve acá sólo
    con `estado=registrado_log` o `estado=todos`."""
    with tenant_session(identidad.tenant_id) as s:
        return notificaciones.envios(s, identidad, p, estado, job_id)


# --------------------------------------------------------------------------- score


@router.get("/consultas/score_documental")
def score_documental(identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return score.consulta(s, identidad)


# --------------------------------------------------------------------------- exportación


@router.get("/consultas/exportar_legajo")
def exportar_legajo(sujeto_id: str = Query(...), formato: Literal["json", "csv"] = Query("json"), identidad: Identidad = Depends(identidad_actual)) -> Response:
    with tenant_session(identidad.tenant_id) as s:
        ct, contenido, nombre = exportacion.exportar(s, identidad, sujeto_id, formato)
    return Response(content=contenido, media_type=ct, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# --------------------------------------------------------------------------- drive


class ConfigurarDriveBody(BaseModel):
    habilitado: bool = False
    carpeta_id: str | None = Field(None, max_length=200)
    intervalo_horas: int | None = Field(None, ge=1, le=168)


class EscanearDriveBody(BaseModel):
    motivo: str | None = None


class ResolverArchivoDriveBody(BaseModel):
    archivo_drive_id: str
    sujeto_id: str = Field(min_length=1)
    requisito_definicion_id: str
    vigente_desde: date
    vigente_hasta: date


class DescartarArchivoDriveBody(BaseModel):
    archivo_drive_id: str
    motivo: str | None = None


@router.post("/comandos/configurar_drive")
def configurar_drive(body: ConfigurarDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: drive.configurar(s, identidad, **body.model_dump()),
                            ruta="/comandos/configurar_drive", body=body.model_dump(mode="json"))


@router.post("/comandos/escanear_drive")
def escanear_drive(body: EscanearDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION),
                            lambda s: drive.escanear(s, identidad, _proveedor_drive(), _storage()),
                            ruta="/comandos/escanear_drive", body=body.model_dump(mode="json"))


@router.post("/comandos/resolver_archivo_drive")
def resolver_archivo_drive(body: ResolverArchivoDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
                            lambda s: drive.resolver(s, identidad, _proveedor_drive(), _storage(), **body.model_dump()),
                            ruta="/comandos/resolver_archivo_drive", body=body.model_dump(mode="json"))


@router.post("/comandos/descartar_archivo_drive")
def descartar_archivo_drive(body: DescartarArchivoDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> dict[str, Any]:
    return ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,), lambda s: drive.descartar(s, identidad, **body.model_dump()),
                            ruta="/comandos/descartar_archivo_drive", body=body.model_dump(mode="json"))


@router.get("/consultas/configuracion_drive")
def configuracion_drive(identidad: Identidad = Depends(identidad_actual)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return drive.configuracion(s, identidad)


@router.get("/consultas/bandeja_drive")
def bandeja_drive(estado: Literal["pendiente_revision", "importado", "descartado", "todos"] = Query("pendiente_revision"),
                  identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> dict:
    with tenant_session(identidad.tenant_id) as s:
        return drive.bandeja(s, identidad, p, None if estado == "todos" else estado)
