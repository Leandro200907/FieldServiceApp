"""Pruebas puras y de arquitectura del radar documental nuevo."""
from datetime import date
from pathlib import Path

from app.core.estado_documental import EstadoRequisitoDocumental, ResultadoRequisitoDocumental
from app.core.radar_documental import resumir_oc, resumir_resultados


def resultado(estado, quiebre=None):
    return ResultadoRequisitoDocumental(estado, quiebre, None, "motivo")


def test_alerta_confirmada_tiene_prioridad_sobre_informacion_incompleta():
    resumen = resumir_resultados([
        resultado(EstadoRequisitoDocumental.PENDIENTE_REVISION),
        resultado(EstadoRequisitoDocumental.FALTANTE, date(2026, 10, 1)),
    ])
    assert resumen.estado == "con_alertas_documentales"
    assert resumen.primer_quiebre == date(2026, 10, 1)


def test_dato_pendiente_produce_informacion_incompleta():
    resumen = resumir_resultados([resultado(EstadoRequisitoDocumental.PENDIENTE_REVISION)])
    assert resumen.estado == "informacion_incompleta"


def test_resultados_vigentes_no_crean_alerta():
    resumen = resumir_resultados([resultado(EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO)])
    assert resumen.estado == "sin_alertas_documentales"


def test_sin_matriz_tiene_precedencia_en_la_oc():
    legajo = resumir_resultados([resultado(EstadoRequisitoDocumental.FALTANTE)])
    assert resumir_oc([legajo], sin_matriz=True).estado == "sin_matriz"


def test_radar_no_depende_de_componentes_operativos():
    fuente = (Path(__file__).parents[1] / "app/modules/radar_documental/servicio.py").read_text(encoding="utf-8")
    prohibidos = ("app.modules.operacion", "modulo1.asignacion_supervisor", "modulo1.custodia_recurso",
                  "modulo1.periodo_custodia", "modulo1.evaluacion_habilitacion", "modulo1.excepcion")
    assert not any(nombre in fuente for nombre in prohibidos)


def test_respuesta_no_introduce_semantica_de_planificacion():
    fuente = (Path(__file__).parents[1] / "app/modules/radar_documental/router.py").read_text(encoding="utf-8")
    prohibidos = ("asignable", "candidato", "capacidad_documental", "bajo_excepcion")
    assert not any(nombre in fuente for nombre in prohibidos)

