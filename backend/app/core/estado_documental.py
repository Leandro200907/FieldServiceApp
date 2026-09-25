"""Evaluación documental pura para el radar del backlog.

Este módulo no conoce OC, asignaciones, custodias, excepciones ni decisiones operativas.
Recibe un requisito, un período y evidencias ya cargadas; devuelve un estado documental
explicable. No realiza I/O y usa fechas inclusivas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Iterable


class EstadoRequisitoDocumental(str, Enum):
    VIGENTE_TODO_EL_PERIODO = "vigente_todo_el_periodo"
    VENCE_DURANTE_PERIODO = "vence_durante_periodo"
    VENCIDO_ANTES_INICIO = "vencido_antes_inicio"
    FALTANTE = "faltante"
    PENDIENTE_REVISION = "pendiente_revision"
    EVIDENCIA_INVALIDA = "evidencia_invalida"
    NO_EVALUABLE = "no_evaluable"
    NO_APLICA = "no_aplica"


class EstadoConfirmacionDocumental(str, Enum):
    DECLARADO = "declarado"
    VERIFICADO = "verificado"
    CONFIRMADO_EN_FUENTE = "confirmado_en_fuente"


class EstadoVersionEvidencia(str, Enum):
    VIGENTE = "vigente"
    SUCEDIDA = "sucedida"
    REVERTIDA_POR_LOTE = "revertida_por_lote"
    RECHAZADA = "rechazada"


class EstadoValidacionArchivo(str, Enum):
    SIN_ARCHIVO = "sin_archivo"
    PENDIENTE = "pendiente"
    VALIDO = "valido"
    INVALIDO = "invalido"


@dataclass(frozen=True)
class RequisitoAplicable:
    requisito_definicion_id: str
    nombre: str
    categoria: str
    tipo_sujeto: str
    aplica: bool = True


@dataclass(frozen=True)
class EvidenciaDocumental:
    evidencia_id: str
    requisito_definicion_id: str
    vigente_desde: date | None
    vigente_hasta: date | None
    estado_confirmacion: EstadoConfirmacionDocumental
    estado_version: EstadoVersionEvidencia = EstadoVersionEvidencia.VIGENTE
    archivo_validacion: EstadoValidacionArchivo = EstadoValidacionArchivo.SIN_ARCHIVO


@dataclass(frozen=True)
class EvaluacionDocumentalEntrada:
    periodo_desde: date
    periodo_hasta: date
    requisito: RequisitoAplicable
    evidencias: tuple[EvidenciaDocumental, ...] = ()


@dataclass(frozen=True)
class ResultadoRequisitoDocumental:
    estado: EstadoRequisitoDocumental
    primer_quiebre: date | None
    evidencia_id: str | None
    motivo: str
    accion_sugerida: str | None = None


def _resultado(
    estado: EstadoRequisitoDocumental,
    motivo: str,
    *,
    evidencia: EvidenciaDocumental | None = None,
    primer_quiebre: date | None = None,
    accion: str | None = None,
) -> ResultadoRequisitoDocumental:
    return ResultadoRequisitoDocumental(
        estado=estado,
        primer_quiebre=primer_quiebre,
        evidencia_id=evidencia.evidencia_id if evidencia else None,
        motivo=motivo,
        accion_sugerida=accion,
    )


def _vigentes(evidencias: Iterable[EvidenciaDocumental]) -> list[EvidenciaDocumental]:
    """Descarta versiones históricas sin modificar ni interpretar su auditoría."""
    return [e for e in evidencias if e.estado_version == EstadoVersionEvidencia.VIGENTE]


def evaluar_requisito_documental(
    entrada: EvaluacionDocumentalEntrada,
) -> ResultadoRequisitoDocumental:
    """Evalúa un requisito para un legajo durante un período inclusivo.

    La función elige primero evidencia probada que cubra mejor el período. Evidencias
    declaradas, pendientes o inválidas sólo determinan el resultado cuando no existe una
    evidencia verificada y válida que resuelva el requisito.
    """
    desde, hasta = entrada.periodo_desde, entrada.periodo_hasta
    requisito = entrada.requisito

    if desde > hasta:
        return _resultado(
            EstadoRequisitoDocumental.NO_EVALUABLE,
            "El período de evaluación es inválido: la fecha inicial es posterior a la final",
            accion="Corregir las fechas del período",
        )
    if not requisito.aplica:
        return _resultado(
            EstadoRequisitoDocumental.NO_APLICA,
            f"{requisito.nombre} no aplica a este tipo de legajo",
        )

    evidencias = [
        e for e in _vigentes(entrada.evidencias)
        if e.requisito_definicion_id == requisito.requisito_definicion_id
    ]
    if not evidencias:
        return _resultado(
            EstadoRequisitoDocumental.FALTANTE,
            f"No existe evidencia vigente para {requisito.nombre}",
            primer_quiebre=desde,
            accion="Incorporar la evidencia requerida",
        )

    completas: list[EvidenciaDocumental] = []
    parciales: list[EvidenciaDocumental] = []
    vencidas: list[EvidenciaDocumental] = []
    pendientes: list[EvidenciaDocumental] = []
    invalidas: list[EvidenciaDocumental] = []
    no_evaluables: list[EvidenciaDocumental] = []

    for evidencia in evidencias:
        if evidencia.archivo_validacion == EstadoValidacionArchivo.INVALIDO:
            invalidas.append(evidencia)
            continue
        if evidencia.vigente_desde is None or evidencia.vigente_hasta is None:
            no_evaluables.append(evidencia)
            continue
        if (
            evidencia.estado_confirmacion == EstadoConfirmacionDocumental.DECLARADO
            or evidencia.archivo_validacion == EstadoValidacionArchivo.PENDIENTE
        ):
            pendientes.append(evidencia)
            continue
        if evidencia.vigente_desde <= desde and evidencia.vigente_hasta >= hasta:
            completas.append(evidencia)
        elif evidencia.vigente_desde <= desde <= evidencia.vigente_hasta < hasta:
            parciales.append(evidencia)
        elif evidencia.vigente_hasta < desde:
            vencidas.append(evidencia)
        else:
            no_evaluables.append(evidencia)

    if completas:
        elegida = max(completas, key=lambda e: (e.vigente_hasta, e.vigente_desde, e.evidencia_id))
        return _resultado(
            EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO,
            f"{requisito.nombre} está vigente durante todo el período",
            evidencia=elegida,
        )
    if parciales:
        elegida = max(parciales, key=lambda e: (e.vigente_hasta, e.vigente_desde, e.evidencia_id))
        quiebre = elegida.vigente_hasta + timedelta(days=1)
        return _resultado(
            EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO,
            f"{requisito.nombre} vence durante el período evaluado",
            evidencia=elegida,
            primer_quiebre=quiebre,
            accion=f"Renovar antes del {quiebre.isoformat()}",
        )
    if pendientes:
        elegida = max(
            pendientes,
            key=lambda e: (e.vigente_hasta or date.min, e.vigente_desde or date.min, e.evidencia_id),
        )
        return _resultado(
            EstadoRequisitoDocumental.PENDIENTE_REVISION,
            f"{requisito.nombre} tiene información pendiente de revisión",
            evidencia=elegida,
            primer_quiebre=desde,
            accion="Revisar y confirmar la evidencia",
        )
    if invalidas:
        elegida = max(invalidas, key=lambda e: e.evidencia_id)
        return _resultado(
            EstadoRequisitoDocumental.EVIDENCIA_INVALIDA,
            f"La evidencia de {requisito.nombre} es inválida",
            evidencia=elegida,
            primer_quiebre=desde,
            accion="Reemplazar o volver a validar la evidencia",
        )
    if vencidas:
        elegida = max(vencidas, key=lambda e: (e.vigente_hasta, e.vigente_desde, e.evidencia_id))
        return _resultado(
            EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO,
            f"{requisito.nombre} está vencido antes del inicio del período",
            evidencia=elegida,
            primer_quiebre=desde,
            accion="Renovar antes del inicio del período",
        )

    elegida = max(no_evaluables, key=lambda e: e.evidencia_id) if no_evaluables else None
    return _resultado(
        EstadoRequisitoDocumental.NO_EVALUABLE,
        f"No hay información suficiente para evaluar {requisito.nombre}",
        evidencia=elegida,
        primer_quiebre=desde,
        accion="Completar o corregir los datos de la evidencia",
    )

