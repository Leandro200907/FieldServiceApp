"""Tests de aceptación de las reglas de dominio cerradas en la revisión funcional del
2026-09-18 (ver docs/DECISIONES_DOMINIO.md). Cada test cita la parte de la
especificación que lo sustenta. Si alguno deja de pasar, primero hay que releer esa cita.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from app.core.orquestacion import evaluar_compromiso
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _docs, _ok, _post, _vigentes
from tests.test_orquestacion import (
    armar_escenario,
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_excepcion,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    requisitos_de,
    sesion,  # noqa: F401 - fixture
)

AHORA = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _linea_no_bloqueante_en_ejecucion(s, req_id: str) -> None:
    s.execute(
        text("UPDATE modulo1.linea_requisito SET bloqueante_durante_ejecucion = false WHERE requisito_definicion_id = :r"),
        {"r": req_id},
    )


# =========================================================================== 1. Propuesta del técnico
# 2.2 de especificacion.md: "Al declarar o confirmar una versión nueva del mismo
# requisito+sujeto, la anterior pasa a `sucedida` en la misma operación" y
# "`rechazada` es terminal ... ni participa de la invariante de a lo sumo un vigente —
# es como si nunca hubiera llegado a ser candidata".


def test_propuesta_sucede_al_vigente_y_el_motor_la_ve_como_requiere_revision(cliente_api, tenant_de_prueba, sesion):
    """Mientras la propuesta está pendiente, el sujeto NO prueba habilitación (1.10:
    lo declarado nunca prueba; el motor filtra por vigente y recién ahí mira confianza)."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = _alta_persona(cliente_api, t, "DNI-1", t.sujeto_tecnico)
    v1 = _cargar(cliente_api, t, persona, req, hasta="2026-12-31")["documento_id"]
    prop = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", {
        "sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-09-01", "vigente_hasta": "2027-09-01"}))
    docs = _docs(t, persona, req)
    assert _vigentes(docs) == [prop["documento_id"]]
    assert next(d for d in docs if d["documento_id"] == v1)["estado_version"] == "sucedida"

    # Motor: con la propuesta declarada vigente, el veredicto es requiere_revision.
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_x", "empresa")
    insertar_matriz(sesion, t.tenant_id, clave, {req: "bloqueante_duro"})
    insertar_oc(sesion, t.tenant_id, "OC-prop", clave, date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t.tenant_id, "OC-prop", AHORA, None)
    assert requisitos_de(r, persona)[req]["veredicto"] == "requiere_revision"
    assert r["resultado_de_decision"] == "no_puede_asignarse"


def test_rechazar_propuesta_restaura_el_anterior_y_es_terminal(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = _alta_persona(cliente_api, t, "DNI-2", t.sujeto_tecnico)
    v1 = _cargar(cliente_api, t, persona, req, hasta="2026-12-31")["documento_id"]
    prop = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", {
        "sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-09-01", "vigente_hasta": "2027-09-01"}))["documento_id"]
    r = _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": prop, "motivo": "ilegible"}))
    assert r["restaurado_documento_id"] == v1
    assert _vigentes(_docs(t, persona, req)) == [v1]
    # Terminal: no se rechaza dos veces ni se confirma una rechazada.
    assert _post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": prop}).status_code == 409
    assert _post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": prop}).status_code == 409


def test_rechazo_sobre_cadena_con_lote_revertido_restaura_el_antecesor_no_terminal(cliente_api, tenant_de_prueba):
    """V1 manual → V2 por lote → técnico propone V3 → se revierte el lote (V2 terminal, V3
    sigue vigente) → se rechaza V3: vuelve V1, no queda el sujeto sin vigente."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = _alta_persona(cliente_api, t, "DNI-3", t.sujeto_tecnico)
    v1 = _cargar(cliente_api, t, persona, req, hasta="2026-10-31")["documento_id"]
    lote = str(uuid.uuid4())
    _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": lote, "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-09-01", "vigente_hasta": "2026-12-31"}]}))
    v3 = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", {
        "sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-09-10", "vigente_hasta": "2027-09-10"}))["documento_id"]
    rev = _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote}))
    assert rev["documentos_restaurados"] == []  # V3 seguía vigente: no se restaura nada
    assert _vigentes(_docs(t, persona, req)) == [v3]
    r = _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta", {"documento_id": v3}))
    assert r["restaurado_documento_id"] == v1
    estados = {d["documento_id"]: d["estado_version"] for d in _docs(t, persona, req)}
    assert estados[v1] == "vigente" and estados[v3] == "rechazada"
    assert [e for i, e in estados.items() if i not in (v1, v3)] == ["revertida_por_lote"]


# =========================================================================== 2. Agregación del veredicto
# 1.12 de documentacion-habilitante.md: empresa primero; después "al menos un legajo
# individual de ese tipo que cumpla todos los requisitos"; nunca se compone entre legajos.
# 1.9: vence_durante_el_trabajo "avisa siempre; bloquea solo si bloqueante_durante_ejecucion".
# 4.1 de especificacion.md: bajo_excepcion ⇒ veredicto ∈ {no_habilitado, vence_durante}.


def test_veredicto_global_es_el_peor_de_los_representantes_nunca_mas_favorable(tenant_de_prueba, sesion):
    """Persona A vence durante el trabajo (bloqueante en ejecución), persona B no habilitada:
    la mejor es A, el global es vence_durante_el_trabajo y NO se puede asignar."""
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, "excepcionable")
    insertar_legajo(sesion, t, "persona_0043", "persona")
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 10, 3))
    insertar_oc(sesion, t, "OC-1", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-1", AHORA, None)
    assert r["veredicto_de_cumplimiento"] == "vence_durante_el_trabajo"
    assert r["resultado_de_decision"] == "no_puede_asignarse"
    rep = next(s for s in r["por_sujeto"] if s["representante"] and s["tipo_sujeto"] == "persona")
    assert rep["sujeto_id"] == "persona_0042" and rep["asignable"] is False


def test_vence_durante_el_trabajo_no_bloqueante_en_ejecucion_deja_asignar_con_aviso(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, "bloqueante_duro")
    _linea_no_bloqueante_en_ejecucion(sesion, esc["req_apto"])
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 10, 3))
    insertar_oc(sesion, t, "OC-2", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-2", AHORA, None)
    # El veredicto sigue avisando; la decisión deja asignar.
    assert r["veredicto_de_cumplimiento"] == "vence_durante_el_trabajo"
    assert r["resultado_de_decision"] == "puede_asignarse"
    assert requisitos_de(r, "persona_0042")[esc["req_apto"]]["asignable"] is True


def test_sujeto_bajo_excepcion_cubre_por_delante_de_uno_bloqueado_sin_volver_verde(tenant_de_prueba, sesion):
    """A: vence durante el trabajo (bloqueante en ejecución, sin excepción). B: no habilitada
    pero con excepción con efecto. Cubre B; el resultado es bajo excepción y el veredicto
    global no es habilitado (ck_excepcion_nunca_verde)."""
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, "excepcionable")
    insertar_legajo(sesion, t, "persona_0043", "persona")
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 10, 3))
    insertar_oc(sesion, t, "OC-3", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    primera = evaluar_compromiso(sesion, t, "OC-3", AHORA, None)
    assert primera["resultado_de_decision"] == "no_puede_asignarse"
    insertar_excepcion(sesion, t, primera["referencia_evaluacion"], "persona_0043", esc["req_apto"], "OC-3")
    r = evaluar_compromiso(sesion, t, "OC-3", AHORA, None)
    rep = next(s for s in r["por_sujeto"] if s["representante"] and s["tipo_sujeto"] == "persona")
    assert rep["sujeto_id"] == "persona_0043" and rep["bajo_excepcion"] is True
    assert r["resultado_de_decision"] == "puede_asignarse_bajo_excepcion"
    assert r["veredicto_de_cumplimiento"] == "no_habilitado"


def test_excepcion_parcial_no_alcanza_si_otro_requisito_del_mismo_sujeto_bloquea(tenant_de_prueba, sesion):
    """Nunca se compone: un sujeto con dos requisitos, uno bajo excepción y otro sin
    documento, no es asignable aunque otro sujeto tenga ese segundo requisito."""
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, "excepcionable")
    req_lic = insertar_definicion(sesion, t, "Licencia", "persona")
    sesion.execute(
        text("INSERT INTO modulo1.linea_requisito (matriz_version_id, requisito_definicion_id, tenant_id, clasificacion, "
             "bloqueante_durante_ejecucion) VALUES (:m, :r, :t, 'excepcionable', true)"),
        {"m": esc["matriz_id"], "r": req_lic, "t": t},
    )
    insertar_legajo(sesion, t, "persona_0043", "persona")
    insertar_documento(sesion, t, "persona_0043", req_lic, date(2026, 1, 1), date(2026, 12, 31))  # solo licencia
    insertar_oc(sesion, t, "OC-4", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    primera = evaluar_compromiso(sesion, t, "OC-4", AHORA, None)
    insertar_excepcion(sesion, t, primera["referencia_evaluacion"], "persona_0042", esc["req_apto"], "OC-4")
    r = evaluar_compromiso(sesion, t, "OC-4", AHORA, None)
    assert r["resultado_de_decision"] == "no_puede_asignarse"
    assert all(not s["asignable"] for s in r["por_sujeto"] if s["tipo_sujeto"] == "persona")


def test_sin_legajo_de_empresa_no_se_asigna(tenant_de_prueba, sesion):
    """1.8: la empresa es *siempre evaluada*; sin legajo no hay evidencia → no_habilitado."""
    t = tenant_de_prueba.tenant_id
    clave = clave_de_matriz()
    insertar_legajo(sesion, t, "persona_0042", "persona")
    req_e = insertar_definicion(sesion, t, "ART", "empresa")
    req_p = insertar_definicion(sesion, t, "Apto", "persona")
    insertar_matriz(sesion, t, clave, {req_e: "bloqueante_duro", req_p: "bloqueante_duro"})
    insertar_documento(sesion, t, "persona_0042", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t, "OC-5", clave, date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-5", AHORA, None)
    assert r["veredicto_de_cumplimiento"] == "no_habilitado"
    assert r["resultado_de_decision"] == "no_puede_asignarse"
    assert any(f["tipo_sujeto"] == "empresa" and f["sujeto_id"] is None for f in r["requisitos_faltantes"])


def test_version_de_matriz_es_la_vigente_al_dia_de_ingreso_no_hoy(tenant_de_prueba, sesion):
    """4.1 regla temporal: `version_matriz` es la vigente a `periodo_desde`."""
    t = tenant_de_prueba.tenant_id
    clave = clave_de_matriz()
    insertar_legajo(sesion, t, "empresa_0001", "empresa")
    insertar_legajo(sesion, t, "persona_0042", "persona")
    req = insertar_definicion(sesion, t, "Apto", "persona")
    m1 = insertar_matriz(sesion, t, clave, {req: "excepcionable"}, version=1, vigente_desde=date(2026, 1, 1), vigente_hasta=date(2026, 9, 30))
    m2 = insertar_matriz(sesion, t, clave, {req: "bloqueante_duro"}, version=2, vigente_desde=date(2026, 10, 1))
    insertar_oc(sesion, t, "OC-sep", clave, date(2026, 9, 20), date(2026, 9, 25))
    insertar_oc(sesion, t, "OC-oct", clave, date(2026, 10, 2), date(2026, 10, 5))
    ahora_octubre = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    assert evaluar_compromiso(sesion, t, "OC-sep", ahora_octubre, None)["version_matriz"]["matriz_version_id"] == m1
    assert evaluar_compromiso(sesion, t, "OC-oct", ahora_octubre, None)["version_matriz"]["matriz_version_id"] == m2


# =========================================================================== 3. Lotes
# 2.5 de especificacion.md: al revertir, todo lo creado por el lote se marca
# revertida_por_lote. 2.11 de modelo-dominio.md: reimportación — vigencia posterior →
# renovación; coincide → no hace nada; contradice un dato verificado → rechazada.


def test_revertir_lote_no_pisa_una_carga_manual_posterior(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = _alta_persona(cliente_api, t, "DNI-4")
    v1 = _cargar(cliente_api, t, persona, req, hasta="2026-10-31")["documento_id"]
    lote = str(uuid.uuid4())
    v2 = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": lote, "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-09-01", "vigente_hasta": "2026-12-31"}]}))["documentos"][0]["documento_id"]
    v3 = _cargar(cliente_api, t, persona, req, desde="2026-09-10", hasta="2027-09-10")["documento_id"]
    r = _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote}))
    assert r["documentos_revertidos"] == [v2] and r["documentos_restaurados"] == []
    estados = {d["documento_id"]: d["estado_version"] for d in _docs(t, persona, req)}
    assert estados == {v1: "sucedida", v2: "revertida_por_lote", v3: "vigente"}


def test_reimportar_igual_no_duplica_y_posterior_renueva(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = _alta_persona(cliente_api, t, "DNI-5")
    v1 = _cargar(cliente_api, t, persona, req, desde="2026-03-01", hasta="2026-09-15")["documento_id"]
    r = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": str(uuid.uuid4()), "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-03-01", "vigente_hasta": "2026-09-15"},
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-09-01", "vigente_hasta": "2027-09-01"},
    ]}))
    assert r["filas_aceptadas"] == 2 and r["filas_rechazadas"] == 0
    assert [f["documento_id"] for f in r["filas_sin_cambios"]] == [v1]
    assert len(r["documentos"]) == 1
    assert len(_docs(t, persona, req)) == 2 and len(_vigentes(_docs(t, persona, req))) == 1


def test_reimportar_contradiciendo_un_verificado_se_rechaza(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = _alta_persona(cliente_api, t, "DNI-6")
    v1 = _cargar(cliente_api, t, persona, req, desde="2026-03-01", hasta="2026-09-15")["documento_id"]  # verificado
    r = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": str(uuid.uuid4()), "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-06-30"}]}))
    assert r["filas_rechazadas"] == 1
    assert r["detalle_filas_rechazadas"][0]["codigo"] == "conflicto_con_dato_verificado"
    assert _vigentes(_docs(t, persona, req)) == [v1]


def test_reimportar_sobre_un_declarado_si_entra_como_version_nueva(cliente_api, tenant_de_prueba):
    """Misma confianza (declarado vs planilla): la planilla es el dato más reciente."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = _alta_persona(cliente_api, t, "DNI-7")
    _cargar(cliente_api, t, persona, req, desde="2026-03-01", hasta="2026-09-15", estado_confirmacion="declarado")
    r = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": str(uuid.uuid4()), "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-06-30"}]}))
    assert r["filas_rechazadas"] == 0 and len(r["documentos"]) == 1


# =========================================================================== 4. Universo del supervisor (fuente única)


def test_universo_del_supervisor_es_el_mismo_para_consultas_y_descargas(tenant_de_prueba, sesion):
    from app.auth.alcance import ROLES_CON_TODO_DESCARGA, ROLES_CON_TODO_LECTURA, alcance_de_sujetos, sujeto_en_alcance
    from app.auth.identidad import Identidad, Rol

    t = tenant_de_prueba
    sup = Identidad(t.tenant_id, t.usuarios["supervisor"], frozenset({Rol.SUPERVISOR}))
    conf = Identidad(t.tenant_id, t.usuarios["configuracion"], frozenset({Rol.CONFIGURACION}))
    hoy = date(2026, 9, 18)
    sesion.execute(
        text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
             "VALUES (:t, 'persona_A', :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "u": sup.usuario_id})
    cust = sesion.execute(
        text("INSERT INTO modulo1.custodia_recurso (tenant_id, recurso_id, tipo_recurso) VALUES (:t, 'vehiculo_V', 'vehiculo') "
             "RETURNING custodia_id"), {"t": t.tenant_id}).scalar()
    sesion.execute(
        text("INSERT INTO modulo1.periodo_custodia (tenant_id, custodia_id, custodio_id, desde) VALUES (:t, :c, 'persona_A', '2026-02-01')"),
        {"t": t.tenant_id, "c": cust})

    assert sorted(alcance_de_sujetos(sesion, sup, hoy)) == ["persona_A", "vehiculo_V"]
    assert sujeto_en_alcance(sesion, sup, "vehiculo_V", hoy, ROLES_CON_TODO_DESCARGA)
    assert not sujeto_en_alcance(sesion, sup, "persona_B", hoy, ROLES_CON_TODO_DESCARGA)
    # La única diferencia legítima entre capacidades es quién ve todo (matriz 2.2):
    assert alcance_de_sujetos(sesion, conf, hoy, ROLES_CON_TODO_LECTURA) is None
    assert alcance_de_sujetos(sesion, conf, hoy, ROLES_CON_TODO_DESCARGA) == []
