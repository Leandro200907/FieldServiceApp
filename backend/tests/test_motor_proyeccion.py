"""Motor de quiebres puro (docs/PROYECCION_DOCUMENTAL.md, puntos 5-8) — sin DB, mismo
estándar que tests/test_casos_de_oro.py."""
from __future__ import annotations

from datetime import date

from app.core.proyeccion import Candidato, calcular_intervalos, puntos_de_quiebre
from app.core.tipos import Documento, EstadoConfirmacion, EstadoVersionDocumento

REQ = "req-apto-medico"


def _doc(sujeto_id: str, vigente_desde: date, vigente_hasta: date, requiere_revision: bool = False) -> Documento:
    return Documento(
        documento_id=f"doc-{sujeto_id}", sujeto_id=sujeto_id, requisito_definicion_id=REQ,
        vigente_desde=vigente_desde, vigente_hasta=vigente_hasta,
        estado_confirmacion=EstadoConfirmacion.VERIFICADO, estado_version=EstadoVersionDocumento.VIGENTE,
        archivo_requiere_revision=requiere_revision,
    )


def test_un_solo_intervalo_cuando_nada_vence_en_el_rango():
    doc = _doc("p1", date(2026, 1, 1), date(2027, 12, 31))
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"},
        {("p1", REQ): doc}, date(2026, 9, 1), date(2026, 9, 30),
    )
    assert len(intervalos) == 1
    assert intervalos[0].desde == date(2026, 9, 1) and intervalos[0].hasta == date(2026, 9, 30)
    assert intervalos[0].estado == "sin_riesgos_detectados"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 1}


def test_quiebre_exacto_en_vigente_hasta_mas_uno_nunca_en_vigente_hasta():
    doc = _doc("p1", date(2026, 1, 1), date(2026, 9, 15))
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"},
        {("p1", REQ): doc}, date(2026, 9, 1), date(2026, 9, 30),
    )
    assert [(i.desde, i.hasta, i.estado) for i in intervalos] == [
        (date(2026, 9, 1), date(2026, 9, 15), "sin_riesgos_detectados"),
        (date(2026, 9, 16), date(2026, 9, 30), "bloqueo_confirmado"),
    ]
    # borde inclusivo: el 15 (vigente_hasta) todavía cubre, el 16 (vigente_hasta+1) no.
    assert intervalos[0].capacidad_documental_potencial == {"persona": 1}
    assert intervalos[1].capacidad_documental_potencial == {"persona": 0}


def test_dos_candidatos_con_vencimientos_distintos_da_tres_intervalos_el_del_medio_sigue_verde():
    doc1 = _doc("p1", date(2026, 1, 1), date(2026, 9, 10))
    doc2 = _doc("p2", date(2026, 1, 1), date(2026, 9, 20))
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona"), Candidato("p2", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"},
        {("p1", REQ): doc1, ("p2", REQ): doc2}, date(2026, 9, 1), date(2026, 9, 30),
    )
    assert len(intervalos) == 3
    assert [i.estado for i in intervalos] == ["sin_riesgos_detectados", "sin_riesgos_detectados", "bloqueo_confirmado"]
    assert [i.capacidad_documental_potencial["persona"] for i in intervalos] == [2, 1, 0]
    assert intervalos[1].causas == []  # sigue cubierto (capacidad 1) — no hay causa que explicar


def test_puntos_de_quiebre_recorta_al_rango_pedido():
    doc = _doc("p1", date(2026, 1, 1), date(2026, 8, 1))  # vence ANTES del rango pedido
    assert puntos_de_quiebre({("p1", REQ): doc}, date(2026, 9, 1), date(2026, 9, 30)) == [
        date(2026, 9, 1), date(2026, 10, 1),
    ]


def test_documento_requiere_revision_da_estado_requiere_revision_no_bloqueo():
    doc = _doc("p1", date(2026, 1, 1), date(2027, 1, 1), requiere_revision=True)
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"},
        {("p1", REQ): doc}, date(2026, 9, 1), date(2026, 9, 30),
    )
    assert intervalos[0].estado == "requiere_revision"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 0}


def test_sin_documento_es_bloqueo_no_requiere_revision():
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"},
        {}, date(2026, 9, 1), date(2026, 9, 30),
    )
    assert intervalos[0].estado == "bloqueo_confirmado"


def test_sin_candidatos_de_un_tipo_capacidad_cero_bloqueo():
    intervalos = calcular_intervalos(
        [], {"persona": [REQ]}, {REQ: "Apto médico"}, {}, date(2026, 9, 1), date(2026, 9, 5),
    )
    assert len(intervalos) == 1
    assert intervalos[0].estado == "bloqueo_confirmado"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 0}
