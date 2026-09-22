"""Proyección documental — las 3 consultas nuevas, contra PostgreSQL real
(docs/PROYECCION_DOCUMENTAL.md). Reutiliza los helpers de test_orquestacion.py (mismos
INSERT que arman escenarios para el motor completo) para no duplicar setup."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.db import tenant_session
from app.modules.operacion import servicio as op
from tests import apoyo
from tests.test_orquestacion import (
    clave_de_matriz,
    decidir,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
)
from tests.test_robustez import _ident


def _get(cliente_api, t, rol, ruta, **params):
    return cliente_api.get(f"/v1/consultas/{ruta}", params=params, headers=t.headers(rol))


@pytest.fixture
def hoy(tenant_de_prueba):
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        return hoy_del_tenant(s, tenant_de_prueba.tenant_id)


# --------------------------------------------------------------------------- calendario_vigencias


def test_calendario_vigencias_rango_simple_y_borde_inclusive(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        req = insertar_definicion(s, t.tenant_id, "Apto médico", "persona")
        insertar_legajo(s, t.tenant_id, "persona_cal", "persona")
        insertar_documento(s, t.tenant_id, "persona_cal", req, hoy - timedelta(days=300), hoy + timedelta(days=9))
        apoyo.supervisor_de(s, t, "persona_cal", desde=hoy - timedelta(days=1))
    r = _get(cliente_api, t, "responsable_legajos", "calendario_vigencias", desde=hoy.isoformat(), hasta=(hoy + timedelta(days=9)).isoformat())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hoy"] == hoy.isoformat()
    assert len(body["items"]) == 1 and body["items"][0]["sujeto_id"] == "persona_cal"
    assert body["items"][0]["dias_para_vencer"] == 9
    assert body["advertencia"]
    # un día después del borde: ya no entra.
    r2 = _get(cliente_api, t, "responsable_legajos", "calendario_vigencias", desde=hoy.isoformat(), hasta=(hoy + timedelta(days=8)).isoformat())
    assert r2.json()["total"] == 0


def test_calendario_vigencias_rango_mayor_a_366_da_422(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    r = _get(cliente_api, t, "responsable_legajos", "calendario_vigencias", desde=hoy.isoformat(), hasta=(hoy + timedelta(days=400)).isoformat())
    assert r.status_code == 422


def test_calendario_vigencias_vencido_dentro_del_rango_aparece(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        req = insertar_definicion(s, t.tenant_id, "Apto médico", "persona")
        insertar_legajo(s, t.tenant_id, "persona_venc", "persona")
        insertar_documento(s, t.tenant_id, "persona_venc", req, hoy - timedelta(days=300), hoy - timedelta(days=1))
        apoyo.supervisor_de(s, t, "persona_venc", desde=hoy - timedelta(days=1))
    r = _get(cliente_api, t, "responsable_legajos", "calendario_vigencias", desde=hoy - timedelta(days=5), hasta=hoy, estado="vencido")
    assert r.status_code == 200
    assert any(i["sujeto_id"] == "persona_venc" for i in r.json()["items"])


def test_calendario_vigencias_alcance_supervisor_vs_responsable(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        req = insertar_definicion(s, t.tenant_id, "Apto médico", "persona")
        insertar_legajo(s, t.tenant_id, "persona_fuera_del_universo", "persona")
        insertar_documento(s, t.tenant_id, "persona_fuera_del_universo", req, hoy - timedelta(days=10), hoy + timedelta(days=5))
    r_sup = _get(cliente_api, t, "supervisor", "calendario_vigencias", desde=hoy.isoformat(), hasta=(hoy + timedelta(days=5)).isoformat())
    assert r_sup.json()["total"] == 0  # nadie en su universo
    r_resp = _get(cliente_api, t, "responsable_legajos", "calendario_vigencias", desde=hoy.isoformat(), hasta=(hoy + timedelta(days=5)).isoformat())
    assert any(i["sujeto_id"] == "persona_fuera_del_universo" for i in r_resp.json()["items"])


def test_calendario_vigencias_tecnico_solo_ve_su_propio_legajo(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    yo = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, yo)
        req = insertar_definicion(s, t.tenant_id, "Apto médico", "persona")
        insertar_documento(s, t.tenant_id, yo, req, hoy - timedelta(days=5), hoy + timedelta(days=5))
        insertar_legajo(s, t.tenant_id, "persona_ajena", "persona")
        insertar_documento(s, t.tenant_id, "persona_ajena", req, hoy - timedelta(days=5), hoy + timedelta(days=5))
    r = _get(cliente_api, t, "tecnico", "calendario_vigencias", desde=hoy.isoformat(), hasta=(hoy + timedelta(days=5)).isoformat())
    assert r.status_code == 200, r.text
    assert {i["sujeto_id"] for i in r.json()["items"]} == {yo}


def test_calendario_vigencias_respeta_transferencia_de_custodia_futura(cliente_api, tenant_de_prueba, hoy):
    """El mismo bug de A-01: el vehículo con custodia programada a futuro sigue
    apareciendo en el calendario del custodio ACTUAL, no del futuro."""
    t = tenant_de_prueba
    yo = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, yo)
        apoyo.legajo(s, t.tenant_id, "vehiculo_transf", "vehiculo")
        apoyo.legajo(s, t.tenant_id, "otra_persona", "persona")
        req_v = insertar_definicion(s, t.tenant_id, "VTV", "vehiculo")
        insertar_documento(s, t.tenant_id, "vehiculo_transf", req_v, hoy - timedelta(days=5), hoy + timedelta(days=5))
        op.cambiar_custodia(s, _ident(t, "responsable_legajos"), recurso_id="vehiculo_transf", tipo_recurso="vehiculo",
                             custodio_id=yo, desde=hoy - timedelta(days=30))
        op.cambiar_custodia(s, _ident(t, "responsable_legajos"), recurso_id="vehiculo_transf", tipo_recurso="vehiculo",
                             custodio_id="otra_persona", desde=hoy + timedelta(days=10))
    r = _get(cliente_api, t, "tecnico", "calendario_vigencias", desde=hoy.isoformat(), hasta=(hoy + timedelta(days=5)).isoformat())
    # `yo` no tiene evidencia propia cargada en este escenario — sólo importa que el
    # vehículo en transferencia siga viéndose (el custodio actual, no el futuro).
    assert {i["sujeto_id"] for i in r.json()["items"]} == {"vehiculo_transf"}


# --------------------------------------------------------------------------- proyeccion_documental


def _escenario_oc(s, tenant_id, hoy, *, oc_desde=None, oc_hasta=None, clasificacion="bloqueante_duro"):
    clave = clave_de_matriz()
    req = insertar_definicion(s, tenant_id, f"Apto médico {uuid.uuid4().hex[:6]}", "persona")
    matriz_id = insertar_matriz(s, tenant_id, clave, {req: clasificacion}, vigente_desde=hoy - timedelta(days=365))
    oc_desde = oc_desde or hoy - timedelta(days=30)
    oc_hasta = oc_hasta or hoy + timedelta(days=60)
    commitment_id = f"OC-{uuid.uuid4().hex[:8]}"
    insertar_oc(s, tenant_id, commitment_id, clave, oc_desde, oc_hasta)
    return {"clave": clave, "req": req, "matriz_id": matriz_id, "commitment_id": commitment_id,
            "oc_desde": oc_desde, "oc_hasta": oc_hasta}


def test_proyeccion_sin_matriz_nunca_da_422(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        clave = clave_de_matriz()
        commitment_id = f"OC-{uuid.uuid4().hex[:8]}"
        insertar_oc(s, t.tenant_id, commitment_id, clave, hoy - timedelta(days=5), hoy + timedelta(days=5))
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=commitment_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "sin_matriz" and body["matriz"] is None
    assert body["causas"] and body["causas"][0]["motivo"] and body["causas"][0]["tipo_sujeto"] is None
    backlog = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog").json()
    fila = next(f for f in backlog["items"] if f["commitment_id"] == commitment_id)
    assert fila["estado"] == "sin_matriz"
    assert fila["capacidad_documental_potencial_hoy"] == {}
    assert fila["origen_calculo"] in ("ultima_decision_visible", "candidatos_del_alcance")
    assert fila["motivos_resumidos"] == ["No hay matriz vigente para (cliente_id, locacion_id, tipo_servicio_id) al día de ingreso de la OC"]


def test_proyeccion_pendiente_de_planificacion_sin_candidatos(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)  # matriz sí, pero ningún candidato de tipo persona
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "pendiente_de_planificacion"
    backlog = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog").json()
    fila = next(f for f in backlog["items"] if f["commitment_id"] == esc["commitment_id"])
    assert fila["estado"] == "pendiente_de_planificacion"
    assert fila["capacidad_documental_potencial_hoy"] == {}
    assert fila["motivos_resumidos"] == ["No hay decisión visible para esta OC ni candidatos en el alcance de quien consulta"]


def test_proyeccion_bloqueo_confirmado_desde_el_primer_dia(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_sin_doc", "persona")  # candidato, sin documento
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "bloqueo_confirmado"
    assert body["intervalos"][0]["estado"] == "bloqueo_confirmado"
    assert body["intervalos"][0]["capacidad_documental_potencial"] == {"persona": 0}
    backlog = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog").json()
    fila = next(f for f in backlog["items"] if f["commitment_id"] == esc["commitment_id"])
    assert fila["estado"] == "bloqueo_confirmado"
    assert fila["capacidad_documental_potencial_hoy"] == {"persona": 0}
    assert fila["origen_calculo"] == "candidatos_del_alcance"
    assert fila["motivos_resumidos"] and "persona" in fila["motivos_resumidos"][0]


def test_proyeccion_requiere_revision_documento_declarado(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_declarada", "persona")
        insertar_documento(s, t.tenant_id, "persona_declarada", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=90), confirmacion="declarado")
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    body = r.json()
    assert body["estado"] == "requiere_revision"
    assert body["intervalos"][0]["capacidad_documental_potencial"] == {"persona": 0}  # nunca cuenta como cobertura real
    backlog = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog").json()
    fila = next(f for f in backlog["items"] if f["commitment_id"] == esc["commitment_id"])
    assert fila["estado"] == "requiere_revision"
    assert fila["origen_calculo"] == "candidatos_del_alcance"
    assert fila["motivos_resumidos"] and "revisión" in fila["motivos_resumidos"][0]


def test_proyeccion_riesgo_documental_hoy_verde_futuro_sin_respaldo(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy, oc_hasta=hoy + timedelta(days=20))
        insertar_legajo(s, t.tenant_id, "persona_vence_pronto", "persona")
        insertar_documento(s, t.tenant_id, "persona_vence_pronto", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=5))
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    body = r.json()
    assert body["estado"] == "riesgo_documental"
    assert body["intervalos"][0]["estado"] == "sin_riesgos_detectados"
    assert any(i["estado"] == "bloqueo_confirmado" for i in body["intervalos"][1:])
    backlog = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog").json()
    fila = next(f for f in backlog["items"] if f["commitment_id"] == esc["commitment_id"])
    assert fila["estado"] == "riesgo_documental"
    assert fila["origen_calculo"] == "candidatos_del_alcance"
    # el motivo resumido tiene que salir del intervalo POSTERIOR que rompe (no del primero,
    # que está bien) — mismo texto "ningún candidato... lo cubre" que arma el motor.
    assert fila["motivos_resumidos"] and "ningún candidato" in fila["motivos_resumidos"][0]


def test_proyeccion_mutua_exclusion_un_solo_candidato_de_respaldo_no_es_riesgo(cliente_api, tenant_de_prueba, hoy):
    """Regresión directa del A-02 corregido: un intervalo intermedio con un solo
    candidato de respaldo (capacidad 1, no 0) sigue sin_riesgos_detectados, nunca riesgo."""
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy, oc_hasta=hoy + timedelta(days=30))
        insertar_legajo(s, t.tenant_id, "persona_a", "persona")
        insertar_legajo(s, t.tenant_id, "persona_b", "persona")
        insertar_documento(s, t.tenant_id, "persona_a", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=8))
        insertar_documento(s, t.tenant_id, "persona_b", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=25))
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    body = r.json()
    intervalos = body["intervalos"]
    assert len(intervalos) == 3
    assert [i["estado"] for i in intervalos] == ["sin_riesgos_detectados", "sin_riesgos_detectados", "bloqueo_confirmado"]
    assert intervalos[1]["capacidad_documental_potencial"] == {"persona": 1}
    assert "causas" not in intervalos[1] or not intervalos[1].get("causas")
    assert body["estado"] == "riesgo_documental"


def test_proyeccion_sin_riesgos_detectados_de_punta_a_punta(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_ok", "persona")
        insertar_documento(s, t.tenant_id, "persona_ok", esc["req"], hoy - timedelta(days=100), hoy + timedelta(days=200))
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    body = r.json()
    assert body["estado"] == "sin_riesgos_detectados" and len(body["intervalos"]) == 1


def test_proyeccion_no_modifica_decisiones_historicas(cliente_api, tenant_de_prueba, hoy):
    """Última evaluación visible ≠ recálculo: correr la proyección no toca
    evaluacion_habilitacion de la decisión que usó como base."""
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_decidida", "persona")
        insertar_documento(s, t.tenant_id, "persona_decidida", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=90))
        decidir(s, t.tenant_id, esc["commitment_id"], ahora_utc(), sujetos=["persona_decidida"], usuario="test")
        antes = dict(s.execute(text(
            "SELECT veredicto_de_cumplimiento, resultado_de_decision, snapshot FROM modulo1.evaluacion_habilitacion WHERE commitment_id = :c"
        ), {"c": esc["commitment_id"]}).mappings().first())
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    assert r.status_code == 200, r.text
    assert r.json()["sujetos"]["origen"] == "ultima_decision_visible"
    with tenant_session(t.tenant_id) as s:
        despues = dict(s.execute(text(
            "SELECT veredicto_de_cumplimiento, resultado_de_decision, snapshot FROM modulo1.evaluacion_habilitacion WHERE commitment_id = :c"
        ), {"c": esc["commitment_id"]}).mappings().first())
    assert antes == despues
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'EvaluacionDeHabilitacionRealizada'")).scalar() == 1


def test_proyeccion_supervisor_sin_candidatos_en_su_universo_cae_a_pendiente(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_fuera", "persona")  # nadie asignado al supervisor
    r = _get(cliente_api, t, "supervisor", "proyeccion_documental", commitment_id=esc["commitment_id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sujetos"]["origen"] == "candidatos_del_alcance" and body["sujetos"]["sujeto_ids"] == []
    assert body["estado"] == "pendiente_de_planificacion"
    assert "persona_fuera" not in r.text  # nunca expone sujetos ajenos


def test_proyeccion_detalle_diario_expande_los_mismos_intervalos(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy, oc_hasta=hoy + timedelta(days=10))
        insertar_legajo(s, t.tenant_id, "persona_diario", "persona")
        insertar_documento(s, t.tenant_id, "persona_diario", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=3))
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"], detalle="diario")
    body = r.json()
    assert body["estado_por_dia"][hoy.isoformat()] == body["intervalos"][0]["estado"]
    assert body["estado_por_dia"][(hoy + timedelta(days=4)).isoformat()] == "bloqueo_confirmado"


def test_proyeccion_oc_futura_desde_es_vigencia_desde_no_hoy(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy, oc_desde=hoy + timedelta(days=15), oc_hasta=hoy + timedelta(days=45))
        insertar_legajo(s, t.tenant_id, "persona_futura", "persona")
        insertar_documento(s, t.tenant_id, "persona_futura", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=200))
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    body = r.json()
    assert body["desde"] == esc["oc_desde"].isoformat()  # nunca "hoy" para una OC futura


def test_proyeccion_desde_explicito_anterior_a_vigencia_de_oc_da_422(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental",
             commitment_id=esc["commitment_id"], desde=(esc["oc_desde"] - timedelta(days=1)).isoformat())
    assert r.status_code == 422


# --------------------------------------------------------------------------- proyeccion_documental_backlog


def test_backlog_mismo_estado_que_el_detalle_para_la_misma_ventana(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy, oc_hasta=hoy + timedelta(days=20))
        insertar_legajo(s, t.tenant_id, "persona_backlog", "persona")
        insertar_documento(s, t.tenant_id, "persona_backlog", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=5))
    detalle = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental",
                   commitment_id=esc["commitment_id"], hasta=(hoy + timedelta(days=30)).isoformat()).json()
    backlog = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog", horizonte_dias=30).json()
    fila = next(f for f in backlog["items"] if f["commitment_id"] == esc["commitment_id"])
    assert fila["estado"] == detalle["estado"] == "riesgo_documental"
    assert detalle["hoy"] == hoy.isoformat()
    assert fila["origen_calculo"] == detalle["sujetos"]["origen"] == "candidatos_del_alcance"
    assert fila["motivos_resumidos"] and isinstance(fila["motivos_resumidos"][0], str)


def test_backlog_primer_quiebre_correcto_y_null_cuando_no_hay(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc_riesgo = _escenario_oc(s, t.tenant_id, hoy, oc_hasta=hoy + timedelta(days=20))
        insertar_legajo(s, t.tenant_id, "persona_riesgo", "persona")
        insertar_documento(s, t.tenant_id, "persona_riesgo", esc_riesgo["req"], hoy - timedelta(days=5), hoy + timedelta(days=5))
        esc_verde = _escenario_oc(s, t.tenant_id, hoy, oc_hasta=hoy + timedelta(days=20))
        insertar_legajo(s, t.tenant_id, "persona_verde", "persona")
        insertar_documento(s, t.tenant_id, "persona_verde", esc_verde["req"], hoy - timedelta(days=5), hoy + timedelta(days=200))
    backlog = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog", horizonte_dias=30).json()
    por_id = {f["commitment_id"]: f for f in backlog["items"]}
    assert por_id[esc_riesgo["commitment_id"]]["primer_quiebre"] == (hoy + timedelta(days=6)).isoformat()
    assert por_id[esc_verde["commitment_id"]]["primer_quiebre"] is None


def test_backlog_filtro_por_estado(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc_bloqueo = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_sin_cobertura", "persona")
        esc_verde = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_cubierta", "persona")
        insertar_documento(s, t.tenant_id, "persona_cubierta", esc_verde["req"], hoy - timedelta(days=5), hoy + timedelta(days=200))
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog", estado="bloqueo_confirmado")
    ids = {f["commitment_id"] for f in r.json()["items"]}
    assert esc_bloqueo["commitment_id"] in ids and esc_verde["commitment_id"] not in ids


def test_backlog_alcance_supervisor_una_oc_sin_candidatos_en_su_universo_no_aparece(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_no_supervisada", "persona")
    r = _get(cliente_api, t, "supervisor", "proyeccion_documental_backlog")
    assert esc["commitment_id"] not in {f["commitment_id"] for f in r.json()["items"]}


def test_backlog_horizonte_mayor_a_366_da_422(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog", horizonte_dias=400)
    assert r.status_code == 422


def test_backlog_oc_futura_lejana_entra_con_ventana_completa(cliente_api, tenant_de_prueba, hoy):
    """Regresión directa de A-02: una OC que arranca después de hoy + horizonte_dias NO
    queda excluida ni produce desde > hasta."""
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy, oc_desde=hoy + timedelta(days=100), oc_hasta=hoy + timedelta(days=130))
        insertar_legajo(s, t.tenant_id, "persona_lejana", "persona")
    r = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog", horizonte_dias=30)
    fila = next(f for f in r.json()["items"] if f["commitment_id"] == esc["commitment_id"])
    # matriz sí, hay un candidato (persona_lejana) pero sin documento: bloqueo_confirmado
    # en el primer intervalo de SU PROPIA ventana (empieza en su vigencia_desde, no en hoy).
    assert fila["estado"] == "bloqueo_confirmado"
    assert fila["vigencia_desde"] == esc["oc_desde"].isoformat()
    assert fila["origen_calculo"] == "candidatos_del_alcance"
    assert fila["motivos_resumidos"] and "ningún candidato" in fila["motivos_resumidos"][0]


def test_backlog_paginacion_real(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        for _ in range(3):
            _escenario_oc(s, t.tenant_id, hoy)
    pagina1 = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog", limit=2, offset=0).json()
    pagina2 = _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog", limit=2, offset=2).json()
    assert len(pagina1["items"]) == 2 and pagina1["total"] >= 3
    assert {f["commitment_id"] for f in pagina1["items"]}.isdisjoint({f["commitment_id"] for f in pagina2["items"]})


# --------------------------------------------------------------------------- transversal


def test_advertencia_obligatoria_en_los_tres_endpoints(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    texto = "Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa."
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
    assert _get(cliente_api, t, "responsable_legajos", "calendario_vigencias").json()["advertencia"] == texto
    assert _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"]).json()["advertencia"] == texto
    assert _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog").json()["advertencia"] == texto


def test_ningun_endpoint_escribe_nada(cliente_api, tenant_de_prueba, hoy):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = _escenario_oc(s, t.tenant_id, hoy)
        insertar_legajo(s, t.tenant_id, "persona_lectura", "persona")
        insertar_documento(s, t.tenant_id, "persona_lectura", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=5))
        antes = {
            tabla: s.execute(text(f"SELECT count(*) FROM modulo1.{tabla}")).scalar()
            for tabla in ("event_log", "outbox_events", "evaluacion_habilitacion")
        }
    _get(cliente_api, t, "responsable_legajos", "calendario_vigencias")
    _get(cliente_api, t, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    _get(cliente_api, t, "responsable_legajos", "proyeccion_documental_backlog")
    with tenant_session(t.tenant_id) as s:
        despues = {
            tabla: s.execute(text(f"SELECT count(*) FROM modulo1.{tabla}")).scalar()
            for tabla in ("event_log", "outbox_events", "evaluacion_habilitacion")
        }
    assert antes == despues


def test_aislamiento_entre_tenants(cliente_api, dos_tenants, hoy):
    ta, tb = dos_tenants
    with tenant_session(ta.tenant_id) as s:
        esc = _escenario_oc(s, ta.tenant_id, hoy_del_tenant(s, ta.tenant_id))
        insertar_legajo(s, ta.tenant_id, "persona_a", "persona")
        insertar_documento(s, ta.tenant_id, "persona_a", esc["req"], hoy - timedelta(days=5), hoy + timedelta(days=5))
    r_otro_tenant = _get(cliente_api, tb, "responsable_legajos", "proyeccion_documental", commitment_id=esc["commitment_id"])
    assert r_otro_tenant.status_code == 404
    r_calendario_tb = _get(cliente_api, tb, "responsable_legajos", "calendario_vigencias")
    assert "persona_a" not in r_calendario_tb.text
