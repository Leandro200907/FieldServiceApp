"""GET /v1/consultas/* — lecturas paginadas con `app.comun.paginacion`."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.dependencies import identidad_actual
from app.auth.identidad import Identidad
from app.comun.paginacion import Pagina, pagina
from app.db import tenant_session
from app.modules.consultas import servicio

router = APIRouter()


# --------------------------------------------------------------------------- servicio.py: evidencia vigente

class EvidenciaVigente(BaseModel):
    tipo: str
    id: str
    sujeto_id: str
    requisito_definicion_id: str
    requisito: str | None
    categoria: str | None
    vigente_desde: str
    vigente_hasta: str
    estado_confirmacion: str
    origen_propuesta: bool
    locacion_id: str | None
    vigente_hoy: bool
    dias_para_vencer: int
    vencido: bool


class ResumenLegajo(BaseModel):
    total: int
    vigentes_hoy: int
    vencidos: int


class LegajoDatos(BaseModel):
    legajo_id: str
    sujeto_id: str
    tipo_sujeto: str
    identificador_natural: str
    dado_de_baja_en: str | None
    creado_en: str


class LegajoResponse(BaseModel):
    hoy: str
    legajo: LegajoDatos
    documentos: list[EvidenciaVigente]
    acreditaciones: list[EvidenciaVigente]
    inducciones: list[EvidenciaVigente]
    resumen: ResumenLegajo


class DocumentoPropuesto(BaseModel):
    documento_id: str
    sujeto_id: str
    requisito_definicion_id: str | None
    requisito: str | None
    numero: str | None
    vigente_desde: str
    vigente_hasta: str
    estado_confirmacion: str
    origen: str
    confianza_extraccion: str | None
    creado_en: str
    vigente_hoy: bool
    dias_para_vencer: int
    vencido: bool


class PropuestasPendientesResponse(BaseModel):
    items: list[DocumentoPropuesto]
    total: int
    offset: int
    limit: int


class TableroVencimientosResponse(BaseModel):
    items: list[EvidenciaVigente]
    total: int
    offset: int
    limit: int
    hoy: str
    hasta: str


# --------------------------------------------------------------------------- servicio.py: OC / decisiones

class UltimaDecisionOC(BaseModel):
    referencia_evaluacion: str
    veredicto_de_cumplimiento: str
    resultado_de_decision: str
    creado_en: str


class OcBacklogItem(BaseModel):
    oc_id: str
    clave_origen: str
    referencia: str | None
    cliente_id: str
    locacion_id: str
    tipo_servicio_id: str
    vigencia_desde: str
    vigencia_hasta: str
    estado: str
    lote_id: str | None
    creado_en: str
    actualizado_en: str
    ultima_decision: UltimaDecisionOC | None


class BacklogOcResponse(BaseModel):
    items: list[OcBacklogItem]
    total: int
    offset: int
    limit: int


class RequisitoEvaluado(BaseModel):
    requisito_definicion_id: str
    veredicto: str
    motivo: str | None
    excepcion_aplicable_pero_sin_efecto: bool
    anulacion_detectada: str | None
    nombre: str | None
    categoria: str | None
    clasificacion: str
    origen_clasificacion: str
    bloqueante_durante_ejecucion: bool
    documento_id: str | None
    constancia_id: str | None
    excepcion_id: str | None
    bajo_excepcion: bool
    asignable: bool


class SujetoEvaluado(BaseModel):
    sujeto_id: str
    tipo_sujeto: str
    veredicto: str
    asignable: bool
    bajo_excepcion: bool
    requisitos: list[RequisitoEvaluado]
    representante: bool


class RequisitoFaltante(BaseModel):
    tipo_sujeto: str
    sujeto_id: str | None
    requisito_definicion_id: str | None
    nombre: str | None = None
    veredicto: str
    motivo: str
    bajo_excepcion: bool


class VersionMatrizEvaluada(BaseModel):
    matriz_version_id: str
    version: int


class OcResumenCobertura(BaseModel):
    oc_id: str
    clave_origen: str
    estado: str
    vigencia_desde: str
    vigencia_hasta: str


class CoberturaOcResponse(BaseModel):
    commitment_id: str
    oc: OcResumenCobertura
    modo: str
    veredicto_de_cumplimiento: str
    resultado_de_decision: str
    por_sujeto: list[SujetoEvaluado]
    requisitos_faltantes: list[RequisitoFaltante]
    version_matriz: VersionMatrizEvaluada


class DecisionResumen(BaseModel):
    referencia_evaluacion: str
    commitment_id: str
    veredicto_de_cumplimiento: str
    resultado_de_decision: str
    por_sujeto: list[SujetoEvaluado]
    requisitos_faltantes: list[RequisitoFaltante]
    version_matriz: VersionMatrizEvaluada
    creado_en: str
    sujetos_propuestos: list[str] | None


class DecisionesOcResponse(BaseModel):
    items: list[DecisionResumen]
    total: int
    offset: int
    limit: int


class DecisionDetalle(DecisionResumen):
    snapshot: dict[str, Any]


# --------------------------------------------------------------------------- servicio.py: supervisión / auditoría

class AsignacionSupervisionHistorial(BaseModel):
    asignacion_id: str
    sujeto_id: str
    supervisor_usuario_id: str
    supervisor_nombre: str | None
    desde: str
    hasta: str | None
    estado: str
    asignada_por: str
    creado_en: str


class HistorialSupervisionResponse(BaseModel):
    items: list[AsignacionSupervisionHistorial]
    total: int
    offset: int
    limit: int


class EventoAuditoria(BaseModel):
    id: int
    evento_id: str
    tipo: str
    payload: dict[str, Any]
    ocurrido_en: str


class LogAuditoriaResponse(BaseModel):
    items: list[EventoAuditoria]
    total: int
    offset: int
    limit: int


class LineaMatrizVigente(BaseModel):
    requisito_definicion_id: str
    requisito: str | None
    categoria: str | None
    tipo_sujeto_aplicable: str | None
    clasificacion: str
    bloqueante_durante_ejecucion: bool


class MatrizVigenteResponse(BaseModel):
    matriz_version_id: str
    cliente_id: str
    locacion_id: str
    tipo_servicio_id: str
    version: int
    vigente_desde: str
    vigente_hasta: str | None
    fuente: str | None
    archivo_de_respaldo: str | None
    autor: str | None
    creado_en: str
    fecha_consultada: str
    lineas: list[LineaMatrizVigente]


class CausaIncumplimiento(BaseModel):
    causa_id: str
    requisito_definicion_id: str
    nombre: str | None
    estado: str
    desde: date
    registrada_en: datetime
    regularizada_en: datetime | None


class AvisoIncumplimiento(BaseModel):
    aviso_id: str
    estado: str
    desde: str
    abierto_en: str
    regularizado_en: str | None
    causas: list[CausaIncumplimiento]
    causas_activas: list[str]


class IncumplimientoEmpresaResponse(BaseModel):
    aviso: AvisoIncumplimiento | None


@router.get("/consultas/legajo", response_model=LegajoResponse)
def legajo(sujeto_id: str = Query(...), identidad: Identidad = Depends(identidad_actual)) -> LegajoResponse:
    with tenant_session(identidad.tenant_id) as s:
        return LegajoResponse(**servicio.legajo(s, identidad, sujeto_id))


@router.get("/consultas/propuestas_pendientes", response_model=PropuestasPendientesResponse)
def propuestas_pendientes(identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> PropuestasPendientesResponse:
    with tenant_session(identidad.tenant_id) as s:
        return PropuestasPendientesResponse(**servicio.propuestas_pendientes(s, identidad, p))


@router.get("/consultas/tablero_vencimientos", response_model=TableroVencimientosResponse)
def tablero_vencimientos(
    dias: int = Query(30, ge=0, le=3650),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> TableroVencimientosResponse:
    with tenant_session(identidad.tenant_id) as s:
        return TableroVencimientosResponse(**servicio.tablero_vencimientos(s, identidad, dias, p))


@router.get("/consultas/backlog_oc", response_model=BacklogOcResponse)
def backlog_oc(
    estado: str | None = Query("activo"),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> BacklogOcResponse:
    with tenant_session(identidad.tenant_id) as s:
        return BacklogOcResponse(**servicio.backlog_oc(s, identidad, estado or None, p))


@router.get("/consultas/cobertura_oc", response_model=CoberturaOcResponse)
def cobertura_oc(commitment_id: str = Query(...), identidad: Identidad = Depends(identidad_actual)) -> CoberturaOcResponse:
    with tenant_session(identidad.tenant_id) as s:
        return CoberturaOcResponse(**servicio.cobertura_oc(s, identidad, commitment_id))


@router.get("/consultas/decisiones_oc", response_model=DecisionesOcResponse)
def decisiones_oc(
    commitment_id: str = Query(...), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)
) -> DecisionesOcResponse:
    with tenant_session(identidad.tenant_id) as s:
        return DecisionesOcResponse(**servicio.decisiones_oc(s, identidad, commitment_id, p))


@router.get("/consultas/decision", response_model=DecisionDetalle)
def decision(referencia_evaluacion: str = Query(...), identidad: Identidad = Depends(identidad_actual)) -> DecisionDetalle:
    with tenant_session(identidad.tenant_id) as s:
        return DecisionDetalle(**servicio.decision(s, identidad, referencia_evaluacion))


@router.get("/consultas/historial_supervision", response_model=HistorialSupervisionResponse)
def historial_supervision(
    sujeto_id: str = Query(...), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)
) -> HistorialSupervisionResponse:
    with tenant_session(identidad.tenant_id) as s:
        return HistorialSupervisionResponse(**servicio.historial_supervision(s, identidad, sujeto_id, p))


@router.get("/consultas/log_auditoria", response_model=LogAuditoriaResponse)
def log_auditoria(
    tipo: str | None = Query(None),
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    identidad: Identidad = Depends(identidad_actual),
    p: Pagina = Depends(pagina),
) -> LogAuditoriaResponse:
    with tenant_session(identidad.tenant_id) as s:
        return LogAuditoriaResponse(**servicio.log_auditoria(s, identidad, tipo, desde, hasta, p))


@router.get("/consultas/matriz_vigente", response_model=MatrizVigenteResponse)
def matriz_vigente(
    cliente_id: UUID = Query(...),
    locacion_id: UUID = Query(...),
    tipo_servicio_id: UUID = Query(...),
    fecha: date | None = Query(None),
    identidad: Identidad = Depends(identidad_actual),
) -> MatrizVigenteResponse:
    with tenant_session(identidad.tenant_id) as s:
        return MatrizVigenteResponse(
            **servicio.matriz_vigente(s, identidad, str(cliente_id), str(locacion_id), str(tipo_servicio_id), fecha)
        )


@router.get("/consultas/incumplimiento_empresa", response_model=IncumplimientoEmpresaResponse)
def incumplimiento_empresa(identidad: Identidad = Depends(identidad_actual)) -> IncumplimientoEmpresaResponse:
    with tenant_session(identidad.tenant_id) as s:
        return IncumplimientoEmpresaResponse(**servicio.incumplimiento_empresa(s, identidad))


# --------------------------------------------------------------------------- requisitos/plantillas.py: plantillas globales

class CopiaLocalDefinicion(BaseModel):
    requisito_definicion_id: str
    nombre: str
    locacion_id: str | None
    copiada_de_version: int | None
    activa: bool
    estado: str


class DefinicionGlobalConCopias(BaseModel):
    definicion_global_id: str
    nombre: str
    categoria: str
    tipo_sujeto_aplicable: str
    version: int
    activa: bool
    descripcion: str | None
    actualizado_en: datetime
    estado: str
    copias_locales: list[CopiaLocalDefinicion]


class LineaMatrizGlobal(BaseModel):
    definicion_global_id: str
    nombre: str
    categoria: str
    tipo_sujeto_aplicable: str
    version_definicion: int
    clasificacion: str
    bloqueante_durante_ejecucion: bool


class LineaMatrizCopiaLocal(BaseModel):
    requisito_definicion_id: str
    nombre: str
    definicion_global_id: str | None
    clasificacion: str
    bloqueante_durante_ejecucion: bool


class CopiaLocalMatriz(BaseModel):
    matriz_version_id: str
    cliente_id: str
    locacion_id: str | None
    tipo_servicio_id: str
    version: int
    vigente_desde: date
    vigente_hasta: date | None
    copiada_de_version: int | None
    estado: str
    lineas: list[LineaMatrizCopiaLocal]


class MatrizGlobalConCopias(BaseModel):
    matriz_global_id: str
    operadora: str
    tipo_servicio: str
    descripcion: str | None
    version: int
    fuente: str | None
    actualizado_en: datetime
    lineas: list[LineaMatrizGlobal]
    estado: str
    copias_locales: list[CopiaLocalMatriz]


class PlantillasGlobalesResponse(BaseModel):
    definiciones: list[DefinicionGlobalConCopias]
    matrices: list[MatrizGlobalConCopias]


@router.get("/consultas/plantillas_globales", response_model=PlantillasGlobalesResponse)
def plantillas_globales(identidad: Identidad = Depends(identidad_actual)) -> PlantillasGlobalesResponse:
    """Plantillas de industria junto a las copias locales (estado sin_copia / al_dia /
    actualizacion_disponible) para decidir a mano qué traer (no-funcionales 1.5.3)."""
    from app.modules.requisitos.plantillas import plantillas_globales as _consulta
    with tenant_session(identidad.tenant_id) as s:
        return PlantillasGlobalesResponse(**_consulta(s, identidad))


# --------------------------------------------------------------------------- H-05 / H-06
from typing import Literal  # noqa: E402

from app.modules.consultas import catalogos  # noqa: E402


def _con(fn, identidad, **kw):
    with tenant_session(identidad.tenant_id) as s:
        return fn(s, identidad, **kw)


class RecursoCustodiado(BaseModel):
    tipo_recurso: str
    periodo_id: str
    custodia_desde: date
    hoy: str
    legajo: LegajoDatos
    documentos: list[EvidenciaVigente]
    acreditaciones: list[EvidenciaVigente]
    inducciones: list[EvidenciaVigente]
    resumen: ResumenLegajo


class ResumenMiLegajo(BaseModel):
    vencidos: int
    vigentes_hoy: int


class MiLegajoResponse(BaseModel):
    hoy: str
    persona: LegajoResponse
    recursos_bajo_custodia: list[RecursoCustodiado]
    resumen: ResumenMiLegajo


@router.get("/consultas/mi_legajo", response_model=MiLegajoResponse)
def mi_legajo(identidad: Identidad = Depends(identidad_actual)) -> MiLegajoResponse:
    """Legajo compuesto del técnico: su persona + vehículos/equipos bajo su custodia vigente (H-05)."""
    return MiLegajoResponse(**_con(catalogos.mi_legajo, identidad))


class SujetoItem(BaseModel):
    sujeto_id: str
    tipo_sujeto: str
    identificador_natural: str
    dado_de_baja_en: datetime | None
    creado_en: datetime


class SujetosResponse(BaseModel):
    items: list[SujetoItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/sujetos", response_model=SujetosResponse)
def sujetos(q: str | None = Query(None, max_length=200), tipo_sujeto: Literal["empresa", "persona", "vehiculo", "equipo"] | None = Query(None),
            activos: bool | None = Query(True), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> SujetosResponse:
    return SujetosResponse(**_con(catalogos.sujetos, identidad, p=p, q=q, tipo_sujeto=tipo_sujeto, activos=activos))


class DefinicionRequisitoItem(BaseModel):
    requisito_definicion_id: str
    nombre: str
    categoria: str
    tipo_sujeto_aplicable: str
    locacion_id: str | None
    activa: bool
    definicion_global_id: str | None
    copiada_de_version: int | None
    plazo_aviso_dias: int | None
    creado_en: datetime


class DefinicionesRequisitoResponse(BaseModel):
    items: list[DefinicionRequisitoItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/definiciones_requisito", response_model=DefinicionesRequisitoResponse)
def definiciones_requisito(q: str | None = Query(None, max_length=200), categoria: Literal["documento", "competencia", "induccion"] | None = Query(None),
                           tipo_sujeto_aplicable: Literal["empresa", "persona", "vehiculo", "equipo"] | None = Query(None),
                           activas: bool | None = Query(True), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> DefinicionesRequisitoResponse:
    return DefinicionesRequisitoResponse(**_con(catalogos.definiciones_requisito, identidad, p=p, q=q, categoria=categoria, tipo_sujeto_aplicable=tipo_sujeto_aplicable, activas=activas))


class MatrizItem(BaseModel):
    matriz_version_id: str
    cliente_id: str
    locacion_id: str
    tipo_servicio_id: str
    version: int
    vigente_desde: date
    vigente_hasta: date | None
    fuente: str | None
    autor: str | None
    matriz_global_id: str | None
    copiada_de_version: int | None
    creado_en: datetime
    lineas: int


class MatricesResponse(BaseModel):
    items: list[MatrizItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/matrices", response_model=MatricesResponse)
def matrices(cliente_id: UUID | None = Query(None), solo_vigentes: bool = Query(False),
             identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> MatricesResponse:
    return MatricesResponse(**_con(catalogos.matrices, identidad, p=p, cliente_id=str(cliente_id) if cliente_id else None, solo_vigentes=solo_vigentes))


class UsuarioItem(BaseModel):
    usuario_id: str
    email: str
    nombre: str
    roles: list[str]
    sujeto_id: str | None
    activo: bool
    creado_en: datetime


class UsuariosResponse(BaseModel):
    items: list[UsuarioItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/usuarios", response_model=UsuariosResponse)
def usuarios(q: str | None = Query(None, max_length=200), rol: Literal["configuracion", "responsable_legajos", "supervisor", "tecnico"] | None = Query(None),
             activos: bool | None = Query(True), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> UsuariosResponse:
    return UsuariosResponse(**_con(catalogos.usuarios, identidad, p=p, q=q, rol=rol, activos=activos))


class DocumentoItem(BaseModel):
    documento_id: str
    sujeto_id: str
    requisito_definicion_id: str | None
    requisito: str | None
    version: int
    vigente_desde: date
    vigente_hasta: date
    estado_version: str
    estado_confirmacion: str
    origen: str
    origen_propuesta: bool
    lote_id: str | None
    archivo_estado: str
    creado_en: datetime


class DocumentosResponse(BaseModel):
    items: list[DocumentoItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/documentos", response_model=DocumentosResponse)
def documentos(sujeto_id: str | None = Query(None), estado_version: Literal["vigente", "sucedida", "rechazada", "revertida_por_lote", "todas"] = Query("vigente"),
               estado_confirmacion: Literal["declarado", "verificado", "confirmado_en_fuente"] | None = Query(None),
               archivo_estado: str | None = Query(None, max_length=40), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> DocumentosResponse:
    return DocumentosResponse(**_con(catalogos.documentos, identidad, p=p, sujeto_id=sujeto_id, estado_version=None if estado_version == "todas" else estado_version,
                estado_confirmacion=estado_confirmacion, archivo_estado=archivo_estado))


class ExcepcionItem(BaseModel):
    excepcion_id: str
    referencia_evaluacion: str
    sujeto_id: str
    requisito_definicion_id: str
    requisito: str | None
    commitment_id: str
    estado: str
    otorgada_por: str
    motivo: str
    vigencia: date | None
    evidencia: str | None
    creado_en: datetime


class ExcepcionesResponse(BaseModel):
    items: list[ExcepcionItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/excepciones", response_model=ExcepcionesResponse)
def excepciones(sujeto_id: str | None = Query(None), estado: Literal["otorgada", "revocada", "regularizada", "vencida"] | None = Query("otorgada"),
                commitment_id: str | None = Query(None), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> ExcepcionesResponse:
    return ExcepcionesResponse(**_con(catalogos.excepciones, identidad, p=p, sujeto_id=sujeto_id, estado=estado, commitment_id=commitment_id))


class ConstanciaItem(BaseModel):
    constancia_id: str
    sujeto_id: str
    requisito_definicion_id: str
    requisito: str | None
    cliente_id: str
    commitment_id: str | None
    estado: str
    emisor: str | None
    evidencia: str
    vigencia: date | None
    reemplazada_por: str | None
    registrada_por: str
    creado_en: datetime


class ConstanciasResponse(BaseModel):
    items: list[ConstanciaItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/constancias", response_model=ConstanciasResponse)
def constancias(sujeto_id: str | None = Query(None), estado: Literal["vigente", "vencida", "revocada", "reemplazada"] | None = Query("vigente"),
                cliente_id: UUID | None = Query(None), identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> ConstanciasResponse:
    return ConstanciasResponse(**_con(catalogos.constancias, identidad, p=p, sujeto_id=sujeto_id, estado=estado, cliente_id=str(cliente_id) if cliente_id else None))


class CustodiaItem(BaseModel):
    periodo_id: str
    custodia_id: str
    recurso_id: str
    tipo_recurso: str
    custodio_id: str | None
    desde: date
    hasta: date | None
    estado: str
    corregido_por: str | None
    creado_en: datetime


class CustodiasResponse(BaseModel):
    items: list[CustodiaItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/custodias", response_model=CustodiasResponse)
def custodias(recurso_id: str | None = Query(None), custodio_id: str | None = Query(None), solo_vigentes: bool = Query(False),
              identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> CustodiasResponse:
    return CustodiasResponse(**_con(catalogos.custodias, identidad, p=p, recurso_id=recurso_id, custodio_id=custodio_id, solo_vigentes=solo_vigentes))


class LoteItem(BaseModel):
    lote_id: str
    origen: str
    entidad: str
    estado: str
    filas_totales: int
    filas_aceptadas: int
    filas_rechazadas: int
    fecha: datetime


class LotesResponse(BaseModel):
    items: list[LoteItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/lotes", response_model=LotesResponse)
def lotes(estado: Literal["aplicado", "revertido"] | None = Query(None), entidad: Literal["legajos", "oc"] | None = Query(None),
          identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> LotesResponse:
    return LotesResponse(**_con(catalogos.lotes, identidad, p=p, estado=estado, entidad=entidad))


class AsignacionSupervisorItem(BaseModel):
    asignacion_id: str
    sujeto_id: str
    supervisor_usuario_id: str
    supervisor: str | None
    supervisor_email: str | None
    desde: date
    hasta: date | None
    estado: str
    asignada_por: str
    creado_en: datetime


class AsignacionesSupervisorResponse(BaseModel):
    items: list[AsignacionSupervisorItem]
    total: int
    offset: int
    limit: int


@router.get("/consultas/asignaciones_supervisor", response_model=AsignacionesSupervisorResponse)
def asignaciones_supervisor(supervisor_usuario_id: UUID | None = Query(None), sujeto_id: str | None = Query(None), solo_vigentes: bool = Query(True),
                            identidad: Identidad = Depends(identidad_actual), p: Pagina = Depends(pagina)) -> AsignacionesSupervisorResponse:
    return AsignacionesSupervisorResponse(**_con(catalogos.asignaciones_supervisor, identidad, p=p, supervisor_usuario_id=str(supervisor_usuario_id) if supervisor_usuario_id else None,
                sujeto_id=sujeto_id, solo_vigentes=solo_vigentes))
