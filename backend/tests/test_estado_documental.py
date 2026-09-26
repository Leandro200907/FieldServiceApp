"""Casos unitarios del núcleo documental puro del radar."""
from datetime import date

from app.core.estado_documental import (
    EstadoConfirmacionDocumental,
    EstadoRequisitoDocumental,
    EstadoValidacionArchivo,
    EstadoVersionEvidencia,
    EvaluacionDocumentalEntrada,
    EvidenciaDocumental,
    RequisitoAplicable,
    evaluar_requisito_documental,
)


REQ = RequisitoAplicable("req-apto", "Apto médico", "documento", "persona")
DESDE = date(2026, 10, 18)
HASTA = date(2026, 10, 22)


def evidencia(
    desde=date(2026, 1, 1),
    hasta=date(2026, 12, 31),
    *,
    confirmacion=EstadoConfirmacionDocumental.VERIFICADO,
    validacion=EstadoValidacionArchivo.VALIDO,
    version=EstadoVersionEvidencia.VIGENTE,
    evidencia_id="doc-1",
):
    return EvidenciaDocumental(
        evidencia_id=evidencia_id,
        requisito_definicion_id=REQ.requisito_definicion_id,
        vigente_desde=desde,
        vigente_hasta=hasta,
        estado_confirmacion=confirmacion,
        estado_version=version,
        archivo_validacion=validacion,
    )


def evaluar(*evidencias, requisito=REQ, desde=DESDE, hasta=HASTA):
    return evaluar_requisito_documental(EvaluacionDocumentalEntrada(desde, hasta, requisito, tuple(evidencias)))


def test_evidencia_verificada_cubre_todo_el_periodo():
    resultado = evaluar(evidencia())
    assert resultado.estado == EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO
    assert resultado.primer_quiebre is None
    assert resultado.evidencia_id == "doc-1"


def test_borde_de_vigencia_es_inclusivo():
    resultado = evaluar(evidencia(hasta=HASTA))
    assert resultado.estado == EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO


def test_vencimiento_durante_periodo_informa_primer_dia_sin_cobertura():
    resultado = evaluar(evidencia(hasta=date(2026, 10, 20)))
    assert resultado.estado == EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO
    assert resultado.primer_quiebre == date(2026, 10, 21)


def test_vencido_antes_del_inicio():
    resultado = evaluar(evidencia(hasta=date(2026, 10, 17)))
    assert resultado.estado == EstadoRequisitoDocumental.VENCIDO_ANTES_INICIO
    assert resultado.primer_quiebre == DESDE


def test_sin_evidencia_es_faltante():
    resultado = evaluar()
    assert resultado.estado == EstadoRequisitoDocumental.FALTANTE


def test_dato_declarado_no_se_presenta_como_vigente_probado():
    resultado = evaluar(evidencia(confirmacion=EstadoConfirmacionDocumental.DECLARADO))
    assert resultado.estado == EstadoRequisitoDocumental.PENDIENTE_REVISION


def test_archivo_pendiente_de_validacion_requiere_revision():
    resultado = evaluar(evidencia(validacion=EstadoValidacionArchivo.PENDIENTE))
    assert resultado.estado == EstadoRequisitoDocumental.PENDIENTE_REVISION


def test_archivo_invalido_se_informa_expresamente():
    resultado = evaluar(evidencia(validacion=EstadoValidacionArchivo.INVALIDO))
    assert resultado.estado == EstadoRequisitoDocumental.EVIDENCIA_INVALIDA


def test_version_historica_no_cubre_el_requisito():
    resultado = evaluar(evidencia(version=EstadoVersionEvidencia.SUCEDIDA))
    assert resultado.estado == EstadoRequisitoDocumental.FALTANTE


def test_evidencia_probada_prevalece_sobre_otra_invalida():
    resultado = evaluar(
        evidencia(evidencia_id="doc-valido"),
        evidencia(validacion=EstadoValidacionArchivo.INVALIDO, evidencia_id="doc-invalido"),
    )
    assert resultado.estado == EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO
    assert resultado.evidencia_id == "doc-valido"


def test_fecha_inicial_posterior_a_final_no_es_evaluable():
    resultado = evaluar(evidencia(), desde=date(2026, 10, 23), hasta=date(2026, 10, 22))
    assert resultado.estado == EstadoRequisitoDocumental.NO_EVALUABLE


def test_requisito_no_aplicable():
    requisito = RequisitoAplicable("req-equipo", "Calibración", "documento", "equipo", aplica=False)
    resultado = evaluar(requisito=requisito)
    assert resultado.estado == EstadoRequisitoDocumental.NO_APLICA


def test_fechas_incompletas_no_son_evaluables():
    resultado = evaluar(evidencia(desde=None))
    assert resultado.estado == EstadoRequisitoDocumental.NO_EVALUABLE


def test_evidencia_que_comienza_despues_del_inicio_no_cubre_el_periodo():
    resultado = evaluar(evidencia(desde=date(2026, 10, 19)))
    assert resultado.estado == EstadoRequisitoDocumental.NO_EVALUABLE

