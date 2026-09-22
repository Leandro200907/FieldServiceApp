"""Motor de quiebres puro (docs/PROYECCION_DOCUMENTAL.md, puntos 5-8 y 15bis) — sin DB,
mismo estándar que tests/test_casos_de_oro.py."""
from __future__ import annotations

from datetime import date

from app.core.proyeccion import Candidato, calcular_intervalos, puntos_de_quiebre
from app.core.tipos import (
    Clasificacion,
    Constancia,
    Documento,
    EstadoConfirmacion,
    EstadoConstancia,
    EstadoExcepcion,
    EstadoVersionDocumento,
    Excepcion,
)

REQ = "req-apto-medico"
CLIENTE = "cliente-0001"
OC = "OC-0001"


def _doc(sujeto_id: str, vigente_desde: date, vigente_hasta: date, requiere_revision: bool = False) -> Documento:
    return Documento(
        documento_id=f"doc-{sujeto_id}", sujeto_id=sujeto_id, requisito_definicion_id=REQ,
        vigente_desde=vigente_desde, vigente_hasta=vigente_hasta,
        estado_confirmacion=EstadoConfirmacion.VERIFICADO, estado_version=EstadoVersionDocumento.VIGENTE,
        archivo_requiere_revision=requiere_revision,
    )


def _constancia(vigencia: date | None = None, estado: EstadoConstancia = EstadoConstancia.VIGENTE) -> Constancia:
    return Constancia(
        constancia_id="const-1", sujeto_id="p1", requisito_definicion_id=REQ, cliente_id=CLIENTE,
        estado=estado, commitment_id=None, vigencia=vigencia,
    )


def _excepcion(vigencia: date | None = None) -> Excepcion:
    return Excepcion(
        excepcion_id="exc-1", sujeto_id="p1", requisito_definicion_id=REQ, commitment_id=OC,
        vigencia=vigencia, estado=EstadoExcepcion.OTORGADA,
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


# --------------------------------------------------------------------------- B-01: quiebre en vigente_desde


def test_documento_que_arranca_a_mitad_de_ventana_quiebra_en_vigente_desde():
    """Hallazgo B-01 (auditoría externa 2026-09-22): antes, el motor sólo agregaba
    `vigente_hasta + 1` como quiebre — un alta a mitad de ventana se evaluaba con la
    fecha de inicio del tramo (antes del alta) y quedaba roja todo el tramo, aunque
    después sí cubriera. `evaluar_documento_en_periodo` ya rechazaba `periodo_desde <
    vigente_desde`; faltaba el quiebre que aislara el día exacto."""
    doc = _doc("p1", date(2026, 9, 15), date(2027, 1, 1))
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"},
        {("p1", REQ): doc}, date(2026, 9, 1), date(2026, 9, 30),
    )
    assert [(i.desde, i.hasta, i.estado) for i in intervalos] == [
        (date(2026, 9, 1), date(2026, 9, 14), "bloqueo_confirmado"),
        (date(2026, 9, 15), date(2026, 9, 30), "sin_riesgos_detectados"),
    ]
    assert intervalos[0].capacidad_documental_potencial == {"persona": 0}
    assert intervalos[1].capacidad_documental_potencial == {"persona": 1}


def test_vigente_desde_anterior_o_igual_a_desde_no_agrega_quiebre_de_mas():
    """Contraparte: si el documento ya estaba vigente antes (o exactamente en) el inicio
    del rango pedido, `vigente_desde` no debe generar un quiebre extra — mismo resultado
    que antes de B-01 para el caso ya cubierto por los tests existentes."""
    doc = _doc("p1", date(2026, 1, 1), date(2027, 12, 31))
    assert puntos_de_quiebre({("p1", REQ): doc}, date(2026, 9, 1), date(2026, 9, 30)) == [
        date(2026, 9, 1), date(2026, 10, 1),
    ]
    doc_exacto = _doc("p1", date(2026, 9, 1), date(2027, 12, 31))
    assert puntos_de_quiebre({("p1", REQ): doc_exacto}, date(2026, 9, 1), date(2026, 9, 30)) == [
        date(2026, 9, 1), date(2026, 10, 1),
    ]


# --------------------------------------------------------------------------- B-02: constancias y excepciones


def test_constancia_vigente_rescata_bloqueante_duro():
    """Hallazgo B-02: el diseño (§8) siempre listó excepciones/constancias como quiebres;
    el motor las ignoraba. Una constancia general vigente cubre un requisito
    bloqueante_duro sin documento — mismo criterio que `_evaluar_requisito`."""
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"}, {},
        date(2026, 9, 1), date(2026, 9, 30),
        clasificaciones={REQ: Clasificacion.BLOQUEANTE_DURO.value},
        constancias={("p1", REQ): [_constancia()]},
        cliente_id=CLIENTE, commitment_id=OC,
    )
    assert len(intervalos) == 1
    assert intervalos[0].estado == "sin_riesgos_detectados"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 1}


def test_constancia_no_rescata_requisito_excepcionable():
    """Constancias sólo cubren bloqueante_duro (4.5 de especificacion.md) — con
    excepcionable, la constancia no tiene efecto y el requisito sigue sin cobertura."""
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"}, {},
        date(2026, 9, 1), date(2026, 9, 30),
        clasificaciones={REQ: Clasificacion.EXCEPCIONABLE.value},
        constancias={("p1", REQ): [_constancia()]},
        cliente_id=CLIENTE, commitment_id=OC,
    )
    assert intervalos[0].estado == "bloqueo_confirmado"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 0}


def test_constancia_con_vigencia_acotada_agrega_quiebre_al_vencer():
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"}, {},
        date(2026, 9, 1), date(2026, 9, 30),
        clasificaciones={REQ: Clasificacion.BLOQUEANTE_DURO.value},
        constancias={("p1", REQ): [_constancia(vigencia=date(2026, 9, 10))]},
        cliente_id=CLIENTE, commitment_id=OC,
    )
    assert [(i.desde, i.hasta, i.estado) for i in intervalos] == [
        (date(2026, 9, 1), date(2026, 9, 10), "sin_riesgos_detectados"),
        (date(2026, 9, 11), date(2026, 9, 30), "bloqueo_confirmado"),
    ]


def test_excepcion_otorgada_nunca_vuelve_verde_pero_habilita_capacidad():
    """`ck_excepcion_nunca_verde` (caso de oro 6.5): la excepción no cambia el veredicto
    crudo del documento, pero sí cuenta para `capacidad_documental_potencial` — es
    exactamente la contradicción que B-02 señaló entre `proyeccion_documental` y
    `cobertura_oc` para la misma OC."""
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"}, {},
        date(2026, 9, 1), date(2026, 9, 30),
        clasificaciones={REQ: Clasificacion.EXCEPCIONABLE.value},
        excepciones={("p1", REQ): _excepcion()},
        cliente_id=CLIENTE, commitment_id=OC,
    )
    assert intervalos[0].estado == "sin_riesgos_detectados"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 1}


def test_excepcion_con_clasificacion_bloqueante_duro_no_tiene_efecto():
    """Espejo de `excepcion_tiene_efecto`: sólo aplica si la clasificación VIGENTE del
    requisito es excepcionable — una reclasificación a bloqueante_duro la deja sin
    efecto, aunque siga `otorgada` (caso de oro 6.5)."""
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"}, {},
        date(2026, 9, 1), date(2026, 9, 30),
        clasificaciones={REQ: Clasificacion.BLOQUEANTE_DURO.value},
        excepciones={("p1", REQ): _excepcion()},
        cliente_id=CLIENTE, commitment_id=OC,
    )
    assert intervalos[0].estado == "bloqueo_confirmado"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 0}


def test_excepcion_con_vigencia_acotada_agrega_quiebre_al_vencer():
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"}, {},
        date(2026, 9, 1), date(2026, 9, 30),
        clasificaciones={REQ: Clasificacion.EXCEPCIONABLE.value},
        excepciones={("p1", REQ): _excepcion(vigencia=date(2026, 9, 10))},
        cliente_id=CLIENTE, commitment_id=OC,
    )
    assert [(i.desde, i.hasta, i.estado) for i in intervalos] == [
        (date(2026, 9, 1), date(2026, 9, 10), "sin_riesgos_detectados"),
        (date(2026, 9, 11), date(2026, 9, 30), "bloqueo_confirmado"),
    ]


def test_excepcion_nunca_rescata_requiere_revision():
    """`VEREDICTOS_EXCEPCIONABLES` excluye REQUIERE_REVISION — un documento declarado sin
    confirmar sigue `requiere_revision` aunque haya una excepción otorgada: lo que falta
    arreglar es el dato, no algo que una excepción pueda excusar."""
    doc = _doc("p1", date(2026, 1, 1), date(2027, 1, 1), requiere_revision=True)
    intervalos = calcular_intervalos(
        [Candidato("p1", "persona")], {"persona": [REQ]}, {REQ: "Apto médico"},
        {("p1", REQ): doc}, date(2026, 9, 1), date(2026, 9, 30),
        clasificaciones={REQ: Clasificacion.EXCEPCIONABLE.value},
        excepciones={("p1", REQ): _excepcion()},
        cliente_id=CLIENTE, commitment_id=OC,
    )
    assert intervalos[0].estado == "requiere_revision"
    assert intervalos[0].capacidad_documental_potencial == {"persona": 0}
