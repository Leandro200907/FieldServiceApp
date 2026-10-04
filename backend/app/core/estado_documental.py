"""Evaluación documental pura para el radar del backlog.

Este módulo no conoce OC, asignaciones, custodias, excepciones ni decisiones operativas.
Recibe un requisito, un período y evidencias ya cargadas; devuelve un estado documental
explicable. No realiza I/O y usa fechas inclusivas.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
    PROPUESTA = "propuesta"
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
    accion_sugerida_fecha: date | None = None


def _resultado(
    estado: EstadoRequisitoDocumental,
    motivo: str,
    *,
    evidencia: EvidenciaDocumental | None = None,
    primer_quiebre: date | None = None,
    accion: str | None = None,
    accion_fecha: date | None = None,
) -> ResultadoRequisitoDocumental:
    return ResultadoRequisitoDocumental(
        estado=estado,
        primer_quiebre=primer_quiebre,
        evidencia_id=evidencia.evidencia_id if evidencia else None,
        motivo=motivo,
        accion_sugerida=accion,
        accion_sugerida_fecha=accion_fecha,
    )


def _utilizables(evidencias: Iterable[EvidenciaDocumental]) -> list[EvidenciaDocumental]:
    """La vigente cubre desde su inicio. Las sucedidas sólo cubren días previos a ese inicio."""
    lista = list(evidencias)
    vigentes = [
        e for e in lista
        if e.estado_version in (EstadoVersionEvidencia.VIGENTE, EstadoVersionEvidencia.PROPUESTA)
    ]
    if not vigentes:
        return []
    inicios = [e.vigente_desde for e in vigentes if e.vigente_desde is not None]
    if not inicios:
        return list(vigentes)
    limite = min(inicios) - timedelta(days=1)
    recortadas: list[EvidenciaDocumental] = []
    for e in lista:
        if e.estado_version != EstadoVersionEvidencia.SUCEDIDA:
            continue
        if e.vigente_desde is None or e.vigente_hasta is None:
            continue
        hasta = min(e.vigente_hasta, limite)
        if hasta < e.vigente_desde:
            continue
        recortadas.append(e if hasta == e.vigente_hasta else replace(e, vigente_hasta=hasta))
    return vigentes + recortadas


_ESTADOS_ALERTA_TEMPORAL = frozenset({
    EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO,
    EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO,
    EstadoRequisitoDocumental.FALTANTE,
})


def _cobertura_temporal(
    candidatas: list[EvidenciaDocumental],
    desde: date,
    hasta: date,
    requisito: RequisitoAplicable,
) -> ResultadoRequisitoDocumental:
    """Alertas por calendario (D19: preceden sobre pendiente de revisión por respaldo)."""
    ordenadas = sorted(candidatas, key=lambda e: (e.vigente_desde, e.vigente_hasta, e.evidencia_id))
    iniciales = [e for e in ordenadas if e.vigente_desde <= desde <= e.vigente_hasta]
    if iniciales:
        elegida = max(iniciales, key=lambda e: (e.vigente_hasta, e.vigente_desde, e.evidencia_id))
        cubierto_hasta = elegida.vigente_hasta
        for evidencia in ordenadas:
            if evidencia.vigente_desde <= cubierto_hasta + timedelta(days=1) and evidencia.vigente_hasta > cubierto_hasta:
                cubierto_hasta = evidencia.vigente_hasta
                elegida = evidencia
            if cubierto_hasta >= hasta:
                break
        if cubierto_hasta >= hasta:
            return _resultado(
                EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO,
                f"{requisito.nombre} está vigente durante todo el período",
                evidencia=elegida,
            )
        quiebre = cubierto_hasta + timedelta(days=1)
        return _resultado(
            EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO,
            f"{requisito.nombre} deja un período sin cobertura documental",
            evidencia=elegida,
            primer_quiebre=quiebre,
            accion="Renovar antes del",
            accion_fecha=quiebre,
        )

    futuras = [e for e in ordenadas if e.vigente_desde > desde]
    if futuras:
        elegida = min(futuras, key=lambda e: (e.vigente_desde, e.vigente_hasta, e.evidencia_id))
        return _resultado(
            EstadoRequisitoDocumental.FALTANTE,
            f"{requisito.nombre} no tiene cobertura documental al inicio del período",
            evidencia=elegida,
            primer_quiebre=desde,
            accion="Incorporar evidencia vigente desde el",
            accion_fecha=desde,
        )

    elegida = max(candidatas, key=lambda e: (e.vigente_hasta, e.vigente_desde, e.evidencia_id))
    return _resultado(
        EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO,
        f"{requisito.nombre} está vencido antes del inicio del período",
        evidencia=elegida,
        primer_quiebre=desde,
        accion="Renovar antes del inicio del período",
    )


def _alerta_temporal_sin_respaldo(
    candidatas: list[EvidenciaDocumental],
    desde: date,
    hasta: date,
    requisito: RequisitoAplicable,
    *,
    hay_vigente_no_probada: bool,
) -> ResultadoRequisitoDocumental | None:
    con_fechas = [e for e in candidatas if e.vigente_desde is not None and e.vigente_hasta is not None]
    probadas = [
        e for e in con_fechas
        if e.estado_version == EstadoVersionEvidencia.VIGENTE or not hay_vigente_no_probada
    ]
    if not probadas:
        return None
    resultado = _cobertura_temporal(probadas, desde, hasta, requisito)
    if resultado.estado in _ESTADOS_ALERTA_TEMPORAL:
        return resultado
    return None


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
        e for e in _utilizables(entrada.evidencias)
        if e.requisito_definicion_id == requisito.requisito_definicion_id
    ]
    if not evidencias:
        return _resultado(
            EstadoRequisitoDocumental.FALTANTE,
            f"No existe evidencia vigente para {requisito.nombre}",
            primer_quiebre=desde,
            accion="Incorporar la evidencia requerida",
        )

    validas: list[EvidenciaDocumental] = []
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
            or evidencia.archivo_validacion
            in (
                EstadoValidacionArchivo.PENDIENTE,
                EstadoValidacionArchivo.SIN_ARCHIVO,
            )
        ):
            pendientes.append(evidencia)
            continue
        validas.append(evidencia)

    hay_vigente_no_probada = any(
        e.estado_version == EstadoVersionEvidencia.VIGENTE for e in pendientes + invalidas
    )
    validas_probada = [
        e for e in validas
        if e.estado_version == EstadoVersionEvidencia.VIGENTE or not hay_vigente_no_probada
    ]

    if validas_probada:
        return _cobertura_temporal(validas_probada, desde, hasta, requisito)
    if pendientes:
        con_fechas = [e for e in pendientes if e.vigente_desde is not None and e.vigente_hasta is not None]
        if con_fechas:
            ordenadas = sorted(con_fechas, key=lambda e: (e.vigente_desde, e.vigente_hasta, e.evidencia_id))
            if all(e.vigente_hasta < desde for e in ordenadas):
                elegida = max(ordenadas, key=lambda e: (e.vigente_hasta, e.vigente_desde, e.evidencia_id))
                return _resultado(
                    EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO,
                    f"{requisito.nombre} está vencido antes del inicio del período (sin respaldo que habilite)",
                    evidencia=elegida,
                    primer_quiebre=desde,
                    accion="Renovar y confirmar con respaldo válido",
                )
        elegida = max(
            pendientes,
            key=lambda e: (e.vigente_hasta or date.min, e.vigente_desde or date.min, e.evidencia_id),
        )
        if elegida.archivo_validacion == EstadoValidacionArchivo.SIN_ARCHIVO:
            motivo = f"{requisito.nombre} no tiene respaldo adjunto"
        elif elegida.archivo_validacion == EstadoValidacionArchivo.PENDIENTE:
            motivo = f"{requisito.nombre} tiene respaldo pendiente de validación"
        elif elegida.estado_confirmacion == EstadoConfirmacionDocumental.DECLARADO:
            motivo = f"{requisito.nombre} está solo declarado, sin confirmación"
        else:
            motivo = f"{requisito.nombre} tiene información pendiente de revisión"
        return _resultado(
            EstadoRequisitoDocumental.PENDIENTE_REVISION,
            motivo,
            evidencia=elegida,
            primer_quiebre=desde,
            accion="Revisar y confirmar la evidencia",
        )
    if invalidas:
        con_fechas = [e for e in invalidas if e.vigente_desde is not None and e.vigente_hasta is not None]
        if con_fechas and all(e.vigente_hasta < desde for e in con_fechas):
            elegida = max(con_fechas, key=lambda e: (e.vigente_hasta, e.vigente_desde, e.evidencia_id))
            return _resultado(
                EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO,
                f"{requisito.nombre} está vencido antes del inicio del período",
                evidencia=elegida,
                primer_quiebre=desde,
                accion="Renovar antes del inicio del período",
            )
        elegida = max(invalidas, key=lambda e: e.evidencia_id)
        return _resultado(
            EstadoRequisitoDocumental.EVIDENCIA_INVALIDA,
            f"La evidencia de {requisito.nombre} es inválida",
            evidencia=elegida,
            primer_quiebre=desde,
            accion="Reemplazar o volver a validar la evidencia",
        )
    elegida = max(no_evaluables, key=lambda e: e.evidencia_id) if no_evaluables else None
    return _resultado(
        EstadoRequisitoDocumental.NO_EVALUABLE,
        f"No hay información suficiente para evaluar {requisito.nombre}",
        evidencia=elegida,
        primer_quiebre=desde,
        accion="Completar o corregir los datos de la evidencia",
    )

