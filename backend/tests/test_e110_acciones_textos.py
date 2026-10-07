"""E-110: acciones pendientes — registrar inducción/competencia y efecto «Sin respaldo válido»."""
from __future__ import annotations

from datetime import date

from app.core.consulta_documental import accion_sugerida_para_req, efecto_accion_documental
from app.core.estado_documental import EstadoRequisitoDocumental


def test_accion_induccion_sin_respaldo_no_es_revisar_propuesta():
    req = {
        "categoria": "induccion",
        "estado": EstadoRequisitoDocumental.PENDIENTE_REVISION.value,
        "archivo_validacion": "sin_archivo",
    }
    propuestas = {("persona-1", "req-ind")}
    assert accion_sugerida_para_req(
        req,
        propuestas_pendientes=propuestas,
        sujeto_id="persona-1",
        requisito_definicion_id="req-ind",
    ) == "Registrar inducción"


def test_accion_competencia_faltante_registrar():
    req = {
        "categoria": "competencia",
        "estado": EstadoRequisitoDocumental.FALTANTE.value,
        "evidencia_id": None,
    }
    assert accion_sugerida_para_req(
        req,
        propuestas_pendientes=set(),
        sujeto_id="p",
        requisito_definicion_id="r",
    ) == "Registrar competencia"


def test_accion_induccion_faltante_no_incorporar_documento():
    req = {
        "categoria": "induccion",
        "estado": EstadoRequisitoDocumental.FALTANTE.value,
        "evidencia_id": None,
    }
    assert accion_sugerida_para_req(
        req,
        propuestas_pendientes=set(),
        sujeto_id="p",
        requisito_definicion_id="r",
    ) == "Registrar inducción"


def test_efecto_sin_respaldo_valido_con_tilde():
    hoy = date(2026, 10, 1)
    req = {
        "estado": EstadoRequisitoDocumental.PENDIENTE_REVISION.value,
        "archivo_validacion": "sin_archivo",
    }
    oc = {"vigencia_desde": date(2026, 9, 1), "vigencia_hasta": date(2026, 12, 31)}
    assert efecto_accion_documental(hoy, oc, req, date(2026, 9, 1)) == "Sin respaldo válido · Ya bloquea"
