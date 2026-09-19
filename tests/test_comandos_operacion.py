"""Comandos de Operación vía HTTP (POST /v1/comandos/*): custodia, excepciones,
constancias, evaluación, permisos e idempotencia. Datos de apoyo por SQL directo."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from tests import apoyo

from app.db import tenant_session
from tests.test_orquestacion import (
    armar_escenario,
    contar_eventos,
    insertar_oc,
)


def _post(cliente_api, tenant, rol, comando, body, clave=None):
    return cliente_api.post(f"/v1/comandos/{comando}", json=body, headers=tenant.headers(rol, clave))


def _periodos(tenant_id: str, custodia_id: str) -> list[dict]:
    with tenant_session(tenant_id) as s:
        return [
            dict(f)
            for f in s.execute(
                text(
                    "SELECT periodo_id, custodio_id, desde, hasta, estado, corregido_por FROM modulo1.periodo_custodia "
                    "WHERE custodia_id = :c ORDER BY creado_en"
                ),
                {"c": custodia_id},
            ).mappings()
        ]


# --------------------------------------------------------------------------- custodia


def _legajos_de_custodia(t):
    with tenant_session(t.tenant_id) as s:
        for sujeto, tipo in (("vehiculo_ABC123", "vehiculo"), ("vehiculo_IDEM", "vehiculo"), ("equipo_9", "equipo"),
                             ("persona_0042", "persona"), ("persona_0077", "persona"), ("persona_0043", "persona"), ("p1", "persona")):
            apoyo.legajo(s, t.tenant_id, sujeto, tipo)
            if tipo == "persona":
                apoyo.supervisor_de(s, t, sujeto)


def test_cambiar_custodia_cierra_el_anterior_el_dia_previo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _legajos_de_custodia(t)
    r1 = _post(cliente_api, t, "supervisor", "cambiar_custodia",
               {"recurso_id": "vehiculo_ABC123", "tipo_recurso": "vehiculo", "custodio_id": "persona_0042", "desde": "2026-09-01"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["periodo_cerrado_id"] is None and r1.json()["eventos"] == ["CustodiaCambiada"]
    custodia_id = r1.json()["custodia_id"]

    r2 = _post(cliente_api, t, "supervisor", "cambiar_custodia",
               {"recurso_id": "vehiculo_ABC123", "tipo_recurso": "vehiculo", "custodio_id": "persona_0077", "desde": "2026-09-10"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["custodia_id"] == custodia_id
    assert r2.json()["periodo_cerrado_id"] == r1.json()["periodo_id"]

    periodos = _periodos(t.tenant_id, custodia_id)
    assert len(periodos) == 2
    vigentes = [p for p in periodos if p["estado"] == "vigente"]
    assert len(vigentes) == 1 and vigentes[0]["custodio_id"] == "persona_0077" and vigentes[0]["hasta"] is None
    cerrado = next(p for p in periodos if p["estado"] == "cerrado")
    assert cerrado["hasta"] == date(2026, 9, 9)

    # No se puede abrir un período que empiece antes (o el mismo día) que el vigente.
    r3 = _post(cliente_api, t, "supervisor", "cambiar_custodia",
               {"recurso_id": "vehiculo_ABC123", "tipo_recurso": "vehiculo", "custodio_id": "persona_0042", "desde": "2026-09-10"})
    assert r3.status_code == 409 and r3.json()["error"]["codigo"] == "conflicto"

    with tenant_session(t.tenant_id) as s:
        assert contar_eventos(s, "CustodiaCambiada") == 2
        assert s.execute(text("SELECT count(*) FROM modulo1.custodia_recurso")).scalar() == 1


def test_corregir_custodia_conserva_historia(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _legajos_de_custodia(t)
    r1 = _post(cliente_api, t, "supervisor", "cambiar_custodia",
               {"recurso_id": "equipo_9", "tipo_recurso": "equipo", "custodio_id": "persona_0042", "desde": "2026-09-01"})
    periodo_viejo = r1.json()["periodo_id"]
    r2 = _post(cliente_api, t, "supervisor", "corregir_custodia",
               {"periodo_id": periodo_viejo, "custodio_id": "persona_0043", "desde": "2026-08-30", "motivo": "error de tipeo"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["periodo_corregido_id"] == periodo_viejo and r2.json()["eventos"] == ["CustodiaCorregida"]
    periodos = {str(p["periodo_id"]): p for p in _periodos(t.tenant_id, r1.json()["custodia_id"])}
    viejo = periodos[periodo_viejo]
    nuevo = periodos[r2.json()["periodo_id"]]
    assert viejo["estado"] == "corregido" and str(viejo["corregido_por"]) == r2.json()["periodo_id"]
    assert nuevo["estado"] == "vigente" and nuevo["custodio_id"] == "persona_0043" and nuevo["desde"] == date(2026, 8, 30)

    # Un período ya corregido no se corrige dos veces; el vigente no admite `hasta`.
    assert _post(cliente_api, t, "supervisor", "corregir_custodia", {"periodo_id": periodo_viejo}).status_code == 409
    r4 = _post(cliente_api, t, "supervisor", "corregir_custodia", {"periodo_id": r2.json()["periodo_id"], "hasta": "2026-09-30"})
    assert r4.status_code == 422
    assert _post(cliente_api, t, "supervisor", "corregir_custodia", {"periodo_id": str(uuid.uuid4())}).status_code == 404


def test_idempotency_key_devuelve_el_mismo_resultado_sin_reaplicar(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    _legajos_de_custodia(t)
    body = {"recurso_id": "vehiculo_IDEM", "tipo_recurso": "vehiculo", "custodio_id": "p1", "desde": "2026-09-01"}
    r1 = _post(cliente_api, t, "supervisor", "cambiar_custodia", body, clave="clave-1")
    r2 = _post(cliente_api, t, "supervisor", "cambiar_custodia", body, clave="clave-1")
    assert r1.status_code == 200 and r1.json() == r2.json()
    assert len(_periodos(t.tenant_id, r1.json()["custodia_id"])) == 1


# --------------------------------------------------------------------------- permisos


def test_permisos_por_rol(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    exc = {"referencia_evaluacion": str(uuid.uuid4()), "sujeto_id": "p", "requisito_definicion_id": str(uuid.uuid4()),
           "commitment_id": "OC", "motivo": "m"}
    r = _post(cliente_api, t, "responsable_legajos", "otorgar_excepcion", exc)
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "prohibido"
    r = _post(cliente_api, t, "supervisor", "evaluar_habilitacion", {"commitment_id": "OC", "sujetos_propuestos": ["p"]})
    assert r.status_code == 403 and r.json()["error"]["codigo"] == "prohibido"
    assert _post(cliente_api, t, "tecnico", "cambiar_custodia",
                 {"recurso_id": "v", "tipo_recurso": "vehiculo", "custodio_id": "p", "desde": "2026-09-01"}).status_code == 403
    const = {"sujeto_id": "p", "requisito_definicion_id": str(uuid.uuid4()), "cliente_id": str(uuid.uuid4()), "evidencia": "e"}
    assert _post(cliente_api, t, "supervisor", "registrar_constancia_del_cliente", const).status_code == 403
    assert _post(cliente_api, t, "configuracion", "evaluar_habilitacion", {"commitment_id": "OC", "sujetos_propuestos": ["p"]}).status_code == 403
    # Sin token: 401 con envelope propio.
    assert cliente_api.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC"}).status_code == 401


# --------------------------------------------------------------------------- excepciones


def test_otorgar_excepcion_solo_sobre_excepcionable_y_revocar(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = armar_escenario(s, t.tenant_id, clasificacion_persona="excepcionable")
        insertar_oc(s, t.tenant_id, "OC-1", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))

    # Decisión: solo el responsable, sobre sujetos propuestos (A-04). El supervisor queda
    # con la persona en su universo para poder otorgar la excepción (2.3 §3).
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                       "VALUES (:t, 'persona_0042', :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "u": t.usuarios["supervisor"]})
    assert _post(cliente_api, t, "supervisor", "evaluar_habilitacion",
                 {"commitment_id": "OC-1", "sujetos_propuestos": ["persona_0042"]}).status_code == 403
    ev = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion",
               {"commitment_id": "OC-1", "sujetos_propuestos": ["persona_0042"]})
    assert ev.status_code == 200, ev.text
    referencia = ev.json()["referencia_evaluacion"]
    assert ev.json()["resultado_de_decision"] == "no_puede_asignarse"
    assert ev.json()["eventos"] == ["EvaluacionDeHabilitacionRealizada"]

    # Sobre la empresa: deshabilitado por cierre seguro (DECISIONES §7) con error estable.
    duro = _post(cliente_api, t, "supervisor", "otorgar_excepcion",
                 {"referencia_evaluacion": referencia, "sujeto_id": "empresa_0001", "requisito_definicion_id": esc["req_empresa"],
                  "commitment_id": "OC-1", "motivo": "no"})
    assert duro.status_code == 422 and duro.json()["error"]["codigo"] == "excepcion_de_empresa_deshabilitada"
    # Sobre bloqueante_duro de un sujeto del universo: 422.
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.linea_requisito SET clasificacion = 'bloqueante_duro' WHERE requisito_definicion_id = :r"),
                  {"r": esc["req_apto"]})
    duro = _post(cliente_api, t, "supervisor", "otorgar_excepcion",
                 {"referencia_evaluacion": referencia, "sujeto_id": "persona_0042", "requisito_definicion_id": esc["req_apto"],
                  "commitment_id": "OC-1", "motivo": "no"})
    assert duro.status_code == 422 and duro.json()["error"]["codigo"] == "requisito_no_excepcionable"
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.linea_requisito SET clasificacion = 'excepcionable' WHERE requisito_definicion_id = :r"),
                  {"r": esc["req_apto"]})

    # Evaluación de otro compromiso: 422; evaluación inexistente: 404.
    otro = _post(cliente_api, t, "supervisor", "otorgar_excepcion",
                 {"referencia_evaluacion": referencia, "sujeto_id": "persona_0042", "requisito_definicion_id": esc["req_apto"],
                  "commitment_id": "OC-otra", "motivo": "no"})
    assert otro.status_code == 422
    assert _post(cliente_api, t, "supervisor", "otorgar_excepcion",
                 {"referencia_evaluacion": str(uuid.uuid4()), "sujeto_id": "persona_0042",
                  "requisito_definicion_id": esc["req_apto"], "commitment_id": "OC-1", "motivo": "no"}).status_code == 404

    ok = _post(cliente_api, t, "supervisor", "otorgar_excepcion",
               {"referencia_evaluacion": referencia, "sujeto_id": "persona_0042", "requisito_definicion_id": esc["req_apto"],
                "commitment_id": "OC-1", "motivo": "cubre curso la semana que viene", "vigencia": "2026-10-31"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["eventos"] == ["ExcepcionOtorgada"]
    excepcion_id = ok.json()["excepcion_id"]
    with tenant_session(t.tenant_id) as s:
        fila = s.execute(text("SELECT otorgada_por, estado FROM modulo1.excepcion WHERE excepcion_id = :e"), {"e": excepcion_id}).first()
        assert fila[0] == t.usuarios["supervisor"] and fila[1] == "otorgada"

    # Duplicada: 409. Ahora la evaluación sale bajo excepción, nunca verde.
    assert _post(cliente_api, t, "supervisor", "otorgar_excepcion",
                 {"referencia_evaluacion": referencia, "sujeto_id": "persona_0042", "requisito_definicion_id": esc["req_apto"],
                  "commitment_id": "OC-1", "motivo": "otra vez"}).status_code == 409
    ev2 = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion",
                {"commitment_id": "OC-1", "sujetos_propuestos": ["persona_0042"]}).json()
    assert ev2["veredicto_de_cumplimiento"] == "no_habilitado"
    assert ev2["resultado_de_decision"] == "puede_asignarse_bajo_excepcion"

    rev = _post(cliente_api, t, "supervisor", "revocar_excepcion", {"excepcion_id": excepcion_id, "motivo": "no hizo el curso"})
    assert rev.status_code == 200 and rev.json()["eventos"] == ["ExcepcionRevocada"]
    assert _post(cliente_api, t, "supervisor", "revocar_excepcion", {"excepcion_id": excepcion_id}).status_code == 409
    ev3 = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion", {"commitment_id": "OC-1", "sujetos_propuestos": ["persona_0042"]}).json()
    assert ev3["resultado_de_decision"] == "no_puede_asignarse"


# --------------------------------------------------------------------------- constancias


def test_constancia_solo_sobre_bloqueante_duro_y_reemplazo(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = armar_escenario(s, t.tenant_id, clasificacion_persona="excepcionable")
        insertar_oc(s, t.tenant_id, "OC-1", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    cliente_id = esc["cliente_id"]

    # Sobre excepcionable: 422, tanto específica como general.
    base = {"sujeto_id": "persona_0042", "requisito_definicion_id": esc["req_apto"], "cliente_id": cliente_id, "evidencia": "mail"}
    r = _post(cliente_api, t, "responsable_legajos", "registrar_constancia_del_cliente", {**base, "commitment_id": "OC-1"})
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "requisito_no_bloqueante_duro"
    assert _post(cliente_api, t, "responsable_legajos", "registrar_constancia_del_cliente", base).status_code == 422
    # Compromiso de otro cliente: 422.
    assert _post(cliente_api, t, "responsable_legajos", "registrar_constancia_del_cliente",
                 {**base, "requisito_definicion_id": esc["req_empresa"], "cliente_id": str(uuid.uuid4()),
                  "commitment_id": "OC-1"}).status_code == 422

    # Sobre bloqueante_duro (requisito de empresa), general: OK.
    duro = {"sujeto_id": "empresa_0001", "requisito_definicion_id": esc["req_empresa"], "cliente_id": cliente_id,
            "evidencia": "nota del cliente", "emisor": "HSE cliente"}
    c1 = _post(cliente_api, t, "responsable_legajos", "registrar_constancia_del_cliente", duro)
    assert c1.status_code == 200, c1.text
    assert c1.json()["eventos"] == ["ConstanciaRegistrada"] and c1.json()["constancia_reemplazada_id"] is None

    # Una nueva general reemplaza a la anterior; una específica del compromiso NO la reemplaza.
    c2 = _post(cliente_api, t, "responsable_legajos", "registrar_constancia_del_cliente", {**duro, "vigencia": "2026-12-31"})
    assert c2.status_code == 200, c2.text
    assert c2.json()["constancia_reemplazada_id"] == c1.json()["constancia_id"]
    assert c2.json()["eventos"] == ["ConstanciaReemplazada", "ConstanciaRegistrada"]
    c3 = _post(cliente_api, t, "responsable_legajos", "registrar_constancia_del_cliente", {**duro, "commitment_id": "OC-1"})
    assert c3.status_code == 200 and c3.json()["constancia_reemplazada_id"] is None

    with tenant_session(t.tenant_id) as s:
        filas = {
            str(f["constancia_id"]): dict(f)
            for f in s.execute(text("SELECT constancia_id, estado, reemplazada_por, registrada_por FROM modulo1.constancia_cliente")).mappings()
        }
        assert filas[c1.json()["constancia_id"]]["estado"] == "reemplazada"
        assert str(filas[c1.json()["constancia_id"]]["reemplazada_por"]) == c2.json()["constancia_id"]
        assert filas[c2.json()["constancia_id"]]["estado"] == "vigente"
        assert filas[c2.json()["constancia_id"]]["registrada_por"] == t.usuarios["responsable_legajos"]
        assert contar_eventos(s, "ConstanciaReemplazada") == 1 and contar_eventos(s, "ConstanciaRegistrada") == 3

    rev = _post(cliente_api, t, "responsable_legajos", "revocar_constancia_del_cliente", {"constancia_id": c3.json()["constancia_id"]})
    assert rev.status_code == 200 and rev.json()["eventos"] == ["ConstanciaRevocada"]
    assert _post(cliente_api, t, "responsable_legajos", "revocar_constancia_del_cliente",
                 {"constancia_id": c1.json()["constancia_id"]}).status_code == 409


def test_constancia_cubre_bloqueante_duro_en_evaluacion_http(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        esc = armar_escenario(s, t.tenant_id)  # persona bloqueante_duro sin documento
        insertar_oc(s, t.tenant_id, "OC-1", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    cuerpo = {"commitment_id": "OC-1", "sujetos_propuestos": ["persona_0042"]}
    antes = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion", cuerpo).json()
    assert antes["resultado_de_decision"] == "no_puede_asignarse"
    c = _post(cliente_api, t, "responsable_legajos", "registrar_constancia_del_cliente",
              {"sujeto_id": "persona_0042", "requisito_definicion_id": esc["req_apto"], "cliente_id": esc["cliente_id"],
               "commitment_id": "OC-1", "evidencia": "carta"})
    assert c.status_code == 200, c.text
    despues = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion", cuerpo).json()
    assert despues["resultado_de_decision"] == "puede_asignarse"
    assert despues["referencia_evaluacion"] != antes["referencia_evaluacion"]


def test_evaluar_habilitacion_errores(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    assert _post(cliente_api, t, "supervisor", "evaluar_habilitacion",
                 {"commitment_id": "no-existe", "sujetos_propuestos": ["x"]}).status_code == 403
    r = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion", {"commitment_id": "no-existe", "sujetos_propuestos": ["x"]})
    assert r.status_code == 404 and r.json()["error"]["codigo"] == "no_encontrado"
