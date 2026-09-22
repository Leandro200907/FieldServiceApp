"""Rutas de las capacidades v1 (H-01): canales de notificación, score documental,
exportación de legajo y Drive. Los comandos pasan por `ejecutar_comando` (rol +
idempotencia); las consultas abren `tenant_session` con la identidad del token."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, pagina
from app.comun.reloj import ahora_utc
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


class ConfiguracionCanalesResponse(BaseModel):
    mail_habilitado: bool
    telegram_habilitado: bool
    remitente_nombre: str | None
    actualizado_en: datetime | None
    usuarios_con_telegram: int
    whatsapp: str


class ConfigurarCanalesResponse(ConfiguracionCanalesResponse):
    eventos: list[str]


class VincularTelegramResponse(BaseModel):
    usuario_id: str
    telegram_vinculado: bool
    eventos: list[str]


class EnvioNotificacion(BaseModel):
    envio_id: int
    job_id: int
    canal: str
    destinatario: str
    usuario_id: str | None
    email: str | None
    nombre: str | None
    estado: str
    proveedor_ref: str | None
    error: str | None
    intentos: int
    creado_en: datetime


class EnviosNotificacionResponse(BaseModel):
    items: list[EnvioNotificacion]
    total: int
    offset: int
    limit: int


@router.post("/comandos/configurar_canales", response_model=ConfigurarCanalesResponse)
def configurar_canales(body: ConfigurarCanalesBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> ConfigurarCanalesResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: notificaciones.configurar_canales(s, identidad, **body.model_dump()),
                                 ruta="/comandos/configurar_canales", body=body.model_dump(mode="json"))
    return ConfigurarCanalesResponse(**resultado)


@router.post("/comandos/vincular_telegram", response_model=VincularTelegramResponse)
def vincular_telegram(body: VincularTelegramBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> VincularTelegramResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: notificaciones.vincular_telegram(s, identidad, **body.model_dump()),
                                 ruta="/comandos/vincular_telegram", body=body.model_dump(mode="json"))
    return VincularTelegramResponse(**resultado)


@router.get("/consultas/configuracion_canales", response_model=ConfiguracionCanalesResponse)
def configuracion_canales(identidad: Identidad = Depends(identidad_actual)) -> ConfiguracionCanalesResponse:
    with tenant_session(identidad.tenant_id) as s:
        return ConfiguracionCanalesResponse(**notificaciones.configuracion_canales(s, identidad))


@router.get("/consultas/envios_notificacion", response_model=EnviosNotificacionResponse)
def envios_notificacion(
    estado: Literal["accion_requerida", "enviado", "fallido", "sin_canal", "registrado_log", "todos"] | None = Query(None),
    job_id: int | None = Query(None),
    identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina),
) -> EnviosNotificacionResponse:
    """Trazabilidad de entregas para seguimiento operativo. Por defecto (`estado` sin
    pasar, o `accion_requerida`): sólo `sin_canal` / `fallido` — lo que necesita que
    alguien haga algo. `registrado_log` nunca se cuenta como entrega real; se ve acá sólo
    con `estado=registrado_log` o `estado=todos`."""
    with tenant_session(identidad.tenant_id) as s:
        return EnviosNotificacionResponse(**notificaciones.envios(s, identidad, p, estado, job_id))


# --------------------------------------------------------------------------- score


class PorTipoSujetoScore(BaseModel):
    sujetos: int
    exigidos: int
    cubiertos: int
    score: float


class PeorSujetoScore(BaseModel):
    sujeto_id: str
    tipo_sujeto: str
    exigidos: int
    cubiertos: int
    score: float


class HistorialScore(BaseModel):
    fecha: str
    score: float
    exigidos: int
    cubiertos: int


class ScoreDocumentalResponse(BaseModel):
    fecha: str
    score: float
    exigidos: int
    cubiertos: int
    sujetos: int
    sujetos_completos: int
    por_tipo_sujeto: dict[str, PorTipoSujetoScore]
    peores: list[PeorSujetoScore]
    historial: list[HistorialScore]


@router.get("/consultas/score_documental", response_model=ScoreDocumentalResponse)
def score_documental(identidad: Identidad = Depends(identidad_actual)) -> ScoreDocumentalResponse:
    with tenant_session(identidad.tenant_id) as s:
        return ScoreDocumentalResponse(**score.consulta(s, identidad))


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


class ConfiguracionDriveResponse(BaseModel):
    habilitado: bool
    carpeta_id: str | None
    intervalo_horas: int | None
    ultimo_escaneo_en: datetime | None
    ultimo_escaneo_resultado: dict[str, Any] | None
    proveedor: str
    pendientes_revision: int
    convencion_nombre: str


class ConfigurarDriveResponse(ConfiguracionDriveResponse):
    eventos: list[str]


class EscanearDriveResponse(BaseModel):
    vistos: int
    nuevos: int
    importados: int
    bandeja: int
    ya_vistos: int
    eventos: list[str]


class ResolverArchivoDriveResponse(BaseModel):
    archivo_drive_id: str
    documento_id: str
    eventos: list[str]


class DescartarArchivoDriveResponse(BaseModel):
    archivo_drive_id: str
    eventos: list[str]


class ArchivoEnBandejaDrive(BaseModel):
    archivo_drive_id: str
    id_externo: str
    nombre: str
    mime: str | None
    modificado_externo: datetime | None
    visto_en: datetime
    estado: str
    confianza: str
    extraccion: dict[str, Any]
    motivo: str | None
    documento_id: str | None
    resuelto_por: str | None
    resuelto_en: datetime | None


class BandejaDriveResponse(BaseModel):
    items: list[ArchivoEnBandejaDrive]
    total: int
    offset: int
    limit: int


@router.post("/comandos/configurar_drive", response_model=ConfigurarDriveResponse)
def configurar_drive(body: ConfigurarDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> ConfigurarDriveResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.CONFIGURACION,), lambda s: drive.configurar(s, identidad, **body.model_dump()),
                                 ruta="/comandos/configurar_drive", body=body.model_dump(mode="json"))
    return ConfigurarDriveResponse(**resultado)


@router.post("/comandos/escanear_drive", response_model=EscanearDriveResponse)
def escanear_drive(body: EscanearDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> EscanearDriveResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION),
                                 lambda s: drive.escanear(s, identidad, _proveedor_drive(), _storage(), ahora_utc()),
                                 ruta="/comandos/escanear_drive", body=body.model_dump(mode="json"))
    return EscanearDriveResponse(**resultado)


@router.post("/comandos/resolver_archivo_drive", response_model=ResolverArchivoDriveResponse)
def resolver_archivo_drive(body: ResolverArchivoDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> ResolverArchivoDriveResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,),
                                 lambda s: drive.resolver(s, identidad, _proveedor_drive(), _storage(), **body.model_dump()),
                                 ruta="/comandos/resolver_archivo_drive", body=body.model_dump(mode="json"))
    return ResolverArchivoDriveResponse(**resultado)


@router.post("/comandos/descartar_archivo_drive", response_model=DescartarArchivoDriveResponse)
def descartar_archivo_drive(body: DescartarArchivoDriveBody, identidad: Identidad = Depends(identidad_actual), clave: str | None = Depends(clave_idempotencia)) -> DescartarArchivoDriveResponse:
    resultado = ejecutar_comando(identidad, clave, (Rol.RESPONSABLE_LEGAJOS,), lambda s: drive.descartar(s, identidad, **body.model_dump()),
                                 ruta="/comandos/descartar_archivo_drive", body=body.model_dump(mode="json"))
    return DescartarArchivoDriveResponse(**resultado)


@router.get("/consultas/configuracion_drive", response_model=ConfiguracionDriveResponse)
def configuracion_drive(identidad: Identidad = Depends(identidad_actual)) -> ConfiguracionDriveResponse:
    with tenant_session(identidad.tenant_id) as s:
        return ConfiguracionDriveResponse(**drive.configuracion(s, identidad))


@router.get("/consultas/bandeja_drive", response_model=BandejaDriveResponse)
def bandeja_drive(estado: Literal["pendiente_revision", "importado", "descartado", "todos"] = Query("pendiente_revision"),
                  identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> BandejaDriveResponse:
    with tenant_session(identidad.tenant_id) as s:
        return BandejaDriveResponse(**drive.bandeja(s, identidad, p, None if estado == "todos" else estado))
