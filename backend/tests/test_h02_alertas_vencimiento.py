"""H-02: ciclo completo de la Alerta de vencimiento con reloj controlado (flujo 3.4,
especificación 4.6, modelo-dominio 2.3/2.4): aviso → recordatorio → vencido → escalado;
pausa por acción; resolución sólo por verificación; excepción sobre vencido; reconocimiento;
destinatarios por rol; coalescing por destinatario; parametrización por tenant y por
requisito; OC sin matriz; consultas con alcance por rol."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.alertas import ParametrosAlerta, etapa_de
from app.db import tenant_session
from app.modules.alertas import servicio as alertas
from app.worker.procesos_reloj import control_vencimientos
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post

# Fechas relativas al "hoy" real del tenant: el reloj de control se controla por parámetro,
# pero los comandos (reconocer, verificar) usan el hoy real; VENCE queda a 40 días.
def _hoy_real(t) -> date:
    from app.comun.reloj import hoy_del_tenant
    with tenant_session(t.tenant_id) as s:
        return hoy_del_tenant(s, t.tenant_id)


VENCE = date.today() + timedelta(days=40)


def _ahora(d: date) -> datetime:
    return datetime.combine(d, time(15, 0), tzinfo=timezone.utc)  # 12:00 en Buenos Aires


def _reloj(t, d: date) -> dict:
    with tenant_session(t.tenant_id) as s:
        return control_vencimientos(s, t.tenant_id, _ahora(d))


def _alerta(t, fuente_id: str) -> dict:
    with tenant_session(t.tenant_id) as s:
        return dict(s.execute(text("SELECT * FROM modulo1.alerta_vencimiento WHERE tenant_id = :t AND fuente_id = :f"),
                              {"t": t.tenant_id, "f": fuente_id}).mappings().one())


def _mensajes(t) -> list[dict]:
    with tenant_session(t.tenant_id) as s:
        return [dict(f["payload"]) for f in s.execute(text(
            "SELECT payload FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'notificaciones' AND payload->>'tipo' = 'AlertasDeVencimiento' ORDER BY id"),
            {"t": t.tenant_id}).mappings()]


def _eventos(t, tipo: str, alerta_id: str | None = None) -> int:
    with tenant_session(t.tenant_id) as s:
        return s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tenant_id = :t AND tipo = :tipo AND (CAST(:a AS text) IS NULL OR payload->>'alerta_id' = CAST(:a AS text))"),
                         {"t": t.tenant_id, "tipo": tipo, "a": alerta_id}).scalar()


@pytest.fixture
def esc(cliente_api, tenant_de_prueba):
    """Persona con supervisor asignado y usuario técnico; un documento verificado que vence el 31/12."""
    global VENCE
    t = tenant_de_prueba
    VENCE = _hoy_real(t) + timedelta(days=40)
    req = _alta_def(cliente_api, t, "Apto médico")
    persona = t.sujeto_tecnico
    with tenant_session(t.tenant_id) as s:
        apoyo.legajo(s, t.tenant_id, persona)
        apoyo.supervisor_de(s, t, persona)
    doc = _cargar(cliente_api, t, persona, req, desde="2026-01-01", hasta=VENCE.isoformat())["documento_id"]
    return {"t": t, "req": req, "persona": persona, "doc": doc}


# --------------------------------------------------------------------------- función pura


def test_etapa_es_funcion_determinista_del_tiempo():
    p = ParametrosAlerta(plazo_aviso_dias=30, escalamiento_dias=7)
    assert etapa_de(VENCE, VENCE - timedelta(days=31), p) is None
    assert etapa_de(VENCE, VENCE - timedelta(days=30), p) == "aviso"
    assert etapa_de(VENCE, VENCE - timedelta(days=16), p) == "aviso"
    assert etapa_de(VENCE, VENCE - timedelta(days=15), p) == "recordatorio"
    assert etapa_de(VENCE, VENCE, p) == "recordatorio"           # vence hoy: todavía vigente (6.1)
    assert etapa_de(VENCE, VENCE + timedelta(days=1), p) == "vencido"
    assert etapa_de(VENCE, VENCE + timedelta(days=7), p) == "vencido"
    assert etapa_de(VENCE, VENCE + timedelta(days=8), p) == "escalado"
    assert etapa_de(VENCE, VENCE - timedelta(days=5), ParametrosAlerta(plazo_aviso_dias=10)) == "recordatorio"
    assert etapa_de(VENCE, VENCE - timedelta(days=5), ParametrosAlerta(plazo_aviso_dias=4)) is None


# --------------------------------------------------------------------------- ciclo completo


def test_ciclo_aviso_recordatorio_vencido_escalado_con_destinatarios(esc):
    t, doc = esc["t"], esc["doc"]
    # T-31: nada
    assert _reloj(t, VENCE - timedelta(days=31))["abiertas"] == 0
    # T-30: aviso a técnico + supervisor + responsable, un mensaje por destinatario
    r = _reloj(t, VENCE - timedelta(days=30))
    assert r["abiertas"] == 1 and r["mensajes"] == 3
    a = _alerta(t, doc)
    assert (a["etapa"], a["estado"], a["abierta_en"]) == ("aviso", "abierta", VENCE - timedelta(days=30))
    assert set(a["destinatarios_notificados_en_esta_etapa"]) == {"tecnico", "supervisor", "responsable_legajos"}
    msgs = _mensajes(t)
    assert {(m["destinatario_rol"], m["destinatario_usuario_id"] is not None) for m in msgs} == {("tecnico", True), ("supervisor", True), ("responsable_legajos", False)}
    assert all(m["prioridad"] == "normal" and m["alertas"][0]["etapa"] == "aviso" for m in msgs)
    assert _eventos(t, "AlertaDeVencimientoAbierta") == 1
    # T-29: misma etapa, no repite (coalescing por etapa)
    r = _reloj(t, VENCE - timedelta(days=29))
    assert r["avanzadas"] == 0 and r["mensajes"] == 0 and len(_mensajes(t)) == 3
    # T-15: recordatorio (sin acción) a los mismos
    r = _reloj(t, VENCE - timedelta(days=15))
    assert r["avanzadas"] == 1 and r["mensajes"] == 3 and _alerta(t, doc)["etapa"] == "recordatorio"
    # T+1: vencido → DocumentoVencido, prioridad alta, supervisor incluido
    r = _reloj(t, VENCE + timedelta(days=1))
    a = _alerta(t, doc)
    assert a["etapa"] == "vencido" and a["estado"] == "abierta" and r["vencidas"] == 1
    assert _eventos(t, "DocumentoVencido") == 1
    ultimos = _mensajes(t)[-3:]
    assert all(m["prioridad"] == "alta" for m in ultimos) and {m["destinatario_rol"] for m in ultimos} == {"tecnico", "supervisor", "responsable_legajos"}
    # T+8: escalado al rol configurable (default responsable_legajos), AlertaEscalada
    r = _reloj(t, VENCE + timedelta(days=8))
    a = _alerta(t, doc)
    assert a["etapa"] == "escalado" and a["escalada_en"] == VENCE + timedelta(days=8) and r["escaladas"] == 1
    assert _eventos(t, "AlertaEscalada", str(a["alerta_id"])) == 1
    assert _mensajes(t)[-1]["destinatario_rol"] == "responsable_legajos" and _mensajes(t)[-1]["alertas"][0]["etapa"] == "escalado"
    # T+9: nada nuevo; la etapa nunca retrocede
    assert _reloj(t, VENCE + timedelta(days=9))["mensajes"] == 0


def test_carga_pausa_y_solo_verificacion_resuelve(cliente_api, esc):
    t, doc, req, persona = esc["t"], esc["doc"], esc["req"], esc["persona"]
    _reloj(t, VENCE - timedelta(days=30))
    # el técnico propone una renovación (declarado): pausa; el recordatorio no insiste
    r = _post(cliente_api, t, "tecnico", "proponer_documento",
              {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": (VENCE - timedelta(days=30)).isoformat(), "vigente_hasta": (VENCE + timedelta(days=365)).isoformat()})
    assert r.status_code == 200, r.text
    nuevo = r.json()["documento_id"]
    a = _alerta(t, doc)
    assert a["estado"] == "pausada_por_accion" and a["ultima_accion_tipo"] == "carga_documento" and a["ultima_accion_ref"] == nuevo
    assert _eventos(t, "AlertaPausada", str(a["alerta_id"])) == 1
    antes = len(_mensajes(t))
    assert _reloj(t, VENCE - timedelta(days=15))["mensajes"] == 0 and _alerta(t, doc)["etapa"] == "recordatorio"
    assert len(_mensajes(t)) == antes
    # llega T sin verificación: vuelve a abierta(vencido) — lo declarado no alcanza (1.10)
    _reloj(t, VENCE + timedelta(days=1))
    a = _alerta(t, doc)
    assert (a["etapa"], a["estado"]) == ("vencido", "abierta")
    # el responsable confirma la propuesta → DocumentoVerificado cubre la fuente → resuelta
    assert _post(cliente_api, t, "responsable_legajos", "confirmar_documento", {"documento_id": nuevo}).status_code == 200
    a = _alerta(t, doc)
    assert a["estado"] == "resuelta" and a["resuelta_motivo"] == "verificacion" and a["resuelta_ref"] == nuevo and a["resuelta_en"] is not None
    assert _eventos(t, "AlertaResuelta", str(a["alerta_id"])) == 1
    # el reloj no la toca más; la nueva fuente tendrá su propia alerta cuando toque
    assert _reloj(t, VENCE + timedelta(days=30))["abiertas"] == 0


def test_verificacion_directa_por_responsable_resuelve_y_reemplazo_sin_verificar_no(cliente_api, esc):
    t, doc, req, persona = esc["t"], esc["doc"], esc["req"], esc["persona"]
    _reloj(t, VENCE - timedelta(days=20))
    # carga verificada (responsable) de la renovación: resuelve de inmediato
    r = _cargar(cliente_api, t, persona, req, desde=(VENCE - timedelta(days=30)).isoformat(), hasta=(VENCE + timedelta(days=365)).isoformat())
    a = _alerta(t, doc)
    assert a["estado"] == "resuelta" and a["resuelta_motivo"] == "verificacion" and a["resuelta_ref"] == r["documento_id"]


def test_fuente_sucedida_por_declarado_sigue_viva_y_anulada_resuelve_con_motivo_auditable(cliente_api, esc):
    t, doc, req, persona = esc["t"], esc["doc"], esc["req"], esc["persona"]
    _reloj(t, VENCE - timedelta(days=20))
    # un lote (declarado) sucede al documento: pausa, pero la alerta sigue viva sobre la fecha original
    lote = str(uuid.uuid4())
    _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": lote, "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": (VENCE - timedelta(days=60)).isoformat(), "vigente_hasta": (VENCE + timedelta(days=181)).isoformat()}]}))
    assert _alerta(t, doc)["estado"] == "pausada_por_accion"
    r2 = _reloj(t, VENCE - timedelta(days=19))
    assert r2["resueltas_sin_fuente"] == 0 and _alerta(t, doc)["estado"] == "pausada_por_accion"
    # llega T sin verificar el lote: vencido igual (lo declarado no prueba nada)
    _reloj(t, VENCE + timedelta(days=1))
    assert (_alerta(t, doc)["etapa"], _alerta(t, doc)["estado"]) == ("vencido", "abierta")
    # se revierte el lote: el documento original vuelve a ser la fuente vigente, la alerta sigue
    _ok(_post(cliente_api, t, "responsable_legajos", "revertir_lote", {"lote_id": lote}))
    assert _reloj(t, VENCE + timedelta(days=2))["resueltas_sin_fuente"] == 0
    # baja del sujeto: ya no hay fuente → resuelta con motivo auditable (no "verificacion")
    assert _post(cliente_api, t, "responsable_legajos", "baja_de_sujeto", {"sujeto_id": persona}).status_code == 200
    r3 = _reloj(t, VENCE + timedelta(days=3))
    a = _alerta(t, doc)
    assert r3["resueltas_sin_fuente"] == 1 and a["estado"] == "resuelta" and a["resuelta_motivo"] == "fuente_reemplazada_o_anulada"


def test_excepcion_sobre_vencido_marca_bajo_excepcion_sin_resolver(cliente_api, esc):
    t, doc, req, persona = esc["t"], esc["doc"], esc["req"], esc["persona"]
    from tests.test_orquestacion import insertar_matriz
    _reloj(t, VENCE + timedelta(days=1))
    assert _alerta(t, doc)["etapa"] == "vencido"
    # matriz excepcionable + OC + decisión para poder otorgar la excepción
    with tenant_session(t.tenant_id) as s:
        clave = {"c": str(uuid.uuid4()), "l": str(uuid.uuid4()), "ts": str(uuid.uuid4())}
        insertar_matriz(s, t.tenant_id, clave, {req: "excepcionable"})
        s.execute(text("INSERT INTO modulo1.oc (tenant_id, clave_origen, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta) "
                       "VALUES (:t, 'OC-X', :c, :l, :ts, :d, :h)"), {"t": t.tenant_id, **clave, "d": VENCE + timedelta(days=10), "h": VENCE + timedelta(days=20)})
    ev = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion", {"commitment_id": "OC-X", "sujetos_propuestos": [persona]})
    assert ev.status_code == 200, ev.text
    r = _post(cliente_api, t, "supervisor", "otorgar_excepcion", {"referencia_evaluacion": ev.json()["referencia_evaluacion"], "sujeto_id": persona,
                                                                   "requisito_definicion_id": req, "commitment_id": "OC-X", "motivo": "curso en trámite"})
    assert r.status_code == 200, r.text
    a = _alerta(t, doc)
    assert (a["estado"], a["bajo_excepcion"], a["ultima_accion_tipo"]) == ("abierta", True, "excepcion")
    # sigue escalando: la excepción evita el bloqueo operativo, no resuelve
    _reloj(t, VENCE + timedelta(days=8))
    assert _alerta(t, doc)["etapa"] == "escalado" and _alerta(t, doc)["bajo_excepcion"] is True


def test_reconocer_pausa_notificaciones_pero_no_cierra(cliente_api, esc):
    t, doc = esc["t"], esc["doc"]
    _reloj(t, VENCE - timedelta(days=30))
    a = _alerta(t, doc)
    assert _post(cliente_api, t, "tecnico", "reconocer_alerta", {"alerta_id": str(a["alerta_id"])}).status_code == 403
    r = _post(cliente_api, t, "supervisor", "reconocer_alerta", {"alerta_id": str(a["alerta_id"]), "comentario": "visto"})
    assert r.status_code == 200, r.text
    # el reconocimiento se cuenta desde el hoy REAL: con 30 días cubre T-15 (= hoy + 25)
    assert _post(cliente_api, t, "configuracion", "configurar_alertas", {"reconocimiento_dias": 30}).status_code == 200
    assert _post(cliente_api, t, "supervisor", "reconocer_alerta", {"alerta_id": str(a["alerta_id"])}).status_code == 200
    assert _alerta(t, doc)["reconocida_hasta"] == _hoy_real(t) + timedelta(days=30)
    antes = len(_mensajes(t))
    _reloj(t, VENCE - timedelta(days=15))
    assert _alerta(t, doc)["etapa"] == "recordatorio" and _alerta(t, doc)["estado"] == "abierta" and len(_mensajes(t)) == antes
    # el ciclo sigue: vencido se notifica igual (el reconocimiento no cierra ni frena el vencimiento)
    _reloj(t, VENCE + timedelta(days=1))
    assert _alerta(t, doc)["etapa"] == "vencido" and len(_mensajes(t)) > antes
    # inexistente / fuera de alcance → 404
    assert _post(cliente_api, t, "supervisor", "reconocer_alerta", {"alerta_id": str(uuid.uuid4())}).status_code == 404


def test_parametrizacion_por_tenant_y_por_requisito(cliente_api, esc):
    t, doc, req = esc["t"], esc["doc"], esc["req"]
    r = _post(cliente_api, t, "supervisor", "configurar_alertas", {"plazo_aviso_dias": 10})
    assert r.status_code == 403
    r = _post(cliente_api, t, "configuracion", "configurar_alertas", {"plazo_aviso_dias": 10, "escalamiento_dias": 2, "rol_escalamiento": "supervisor"})
    assert r.status_code == 200 and r.json()["plazo_aviso_dias"] == 10
    cfg = cliente_api.get("/v1/consultas/configuracion_alertas", headers=t.headers("responsable_legajos")).json()
    assert (cfg["plazo_aviso_dias"], cfg["escalamiento_dias"], cfg["rol_escalamiento"]) == (10, 2, "supervisor")
    assert _reloj(t, VENCE - timedelta(days=11))["abiertas"] == 0     # con plazo 10, T-11 no abre
    # override por requisito: 40 días
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.definicion_requisito SET plazo_aviso_dias = 40 WHERE requisito_definicion_id = :r"), {"r": req})
    assert _reloj(t, VENCE - timedelta(days=11))["abiertas"] == 1 and _alerta(t, doc)["etapa"] == "recordatorio"   # 11 <= 40/2
    assert cliente_api.get("/v1/consultas/configuracion_alertas", headers=t.headers("configuracion")).json()["plazos_por_requisito"][0]["plazo_aviso_dias"] == 40
    # escalamiento en T+3 (N=2) al supervisor
    _reloj(t, VENCE + timedelta(days=3))
    assert _alerta(t, doc)["etapa"] == "escalado" and _mensajes(t)[-1]["destinatario_rol"] == "supervisor"


def test_coalescing_por_destinatario_agrupa_varias_alertas_en_un_mensaje(cliente_api, esc):
    t, req, persona = esc["t"], esc["req"], esc["persona"]
    req2 = _alta_def(cliente_api, t, "Altura", categoria="competencia")
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.acreditacion_competencia (tenant_id, persona_id, requisito_definicion_id, vigente_desde, vigente_hasta, evidencias) "
                       "VALUES (:t, :p, :r, '2026-01-01', :h, ARRAY[gen_random_uuid()])"), {"t": t.tenant_id, "p": persona, "r": req2, "h": VENCE})
    r = _reloj(t, VENCE - timedelta(days=30))
    assert r["abiertas"] == 2 and r["notificaciones"] == 6 and r["mensajes"] == 3   # 2 alertas × 3 destinatarios → 3 mensajes
    msgs = _mensajes(t)
    assert all(len(m["alertas"]) == 2 for m in msgs)
    assert {a["fuente_tipo"] for a in msgs[0]["alertas"]} == {"documento", "acreditacion_competencia"}


def test_consultas_abiertas_e_historial_con_alcance_por_rol(cliente_api, esc, dos_tenants):
    t, doc, persona = esc["t"], esc["doc"], esc["persona"]
    _reloj(t, VENCE - timedelta(days=30))
    otra = _alta_persona(cliente_api, t, "DNI 99")  # fuera del universo del supervisor y del técnico
    _cargar(cliente_api, t, otra, esc["req"], desde="2026-01-01", hasta=VENCE.isoformat())
    _reloj(t, VENCE - timedelta(days=29))
    resp = cliente_api.get("/v1/consultas/alertas_abiertas", headers=t.headers("responsable_legajos")).json()
    assert resp["total"] == 2 and resp["por_etapa"] == {"aviso": 2} and {"items", "offset", "limit", "hoy"} <= set(resp)
    sup = cliente_api.get("/v1/consultas/alertas_abiertas", headers=t.headers("supervisor")).json()
    assert sup["total"] == 1 and sup["items"][0]["sujeto_id"] == persona
    tec = cliente_api.get("/v1/consultas/alertas_abiertas", headers=t.headers("tecnico")).json()
    assert tec["total"] == 1 and tec["items"][0]["fuente_id"] == doc
    assert cliente_api.get("/v1/consultas/alertas_abiertas", params={"etapa": "vencido"}, headers=t.headers("responsable_legajos")).json()["total"] == 0
    assert cliente_api.get("/v1/consultas/alertas_abiertas", params={"sujeto_id": otra}, headers=t.headers("supervisor")).json()["total"] == 0
    # historial: incluye resueltas y sus eventos; técnico no lo consulta
    _cargar(cliente_api, t, persona, esc["req"], desde=(VENCE - timedelta(days=30)).isoformat(), hasta=(VENCE + timedelta(days=365)).isoformat())
    h = cliente_api.get("/v1/consultas/historial_alertas", params={"sujeto_id": persona}, headers=t.headers("supervisor")).json()
    assert h["total"] == 1 and h["items"][0]["estado"] == "resuelta" and h["items"][0]["resuelta_motivo"] == "verificacion"
    assert [e["tipo"] for e in h["items"][0]["eventos"]] == ["AlertaDeVencimientoAbierta", "AlertaPausada", "AlertaResuelta"]
    assert cliente_api.get("/v1/consultas/historial_alertas", headers=t.headers("tecnico")).status_code == 403
    # otro tenant no ve nada
    ta, tb = dos_tenants
    assert cliente_api.get("/v1/consultas/alertas_abiertas", headers=tb.headers("responsable_legajos")).json()["total"] == 0


def test_oc_sin_matriz_avisa_una_vez_a_configuracion(esc):
    t = esc["t"]
    with tenant_session(t.tenant_id) as s:
        apoyo.oc(s, t.tenant_id, "OC-SIN-MATRIZ")
    r1 = _reloj(t, VENCE - timedelta(days=60))
    r2 = _reloj(t, VENCE - timedelta(days=59))
    assert r1["oc_sin_matriz"] == 1 and r2["oc_sin_matriz"] == 0
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tenant_id = :t AND tipo = 'OcSinMatriz'"), {"t": t.tenant_id}).scalar() == 1
        job = s.execute(text("SELECT payload FROM modulo1.job_queue WHERE tenant_id = :t AND payload->>'tipo' = 'OcSinMatriz'"), {"t": t.tenant_id}).scalar()
    assert job["destinatario_rol"] == "configuracion" and job["clave_origen"] == "OC-SIN-MATRIZ"


def test_vencimiento_dispara_revaluacion_de_decision_vigente(cliente_api, esc):
    """3.4 cuarta política: DocumentoVencido es cambio de entrada del snapshot (2.2)."""
    t, req, persona = esc["t"], esc["req"], esc["persona"]
    from tests.test_orquestacion import insertar_matriz
    with tenant_session(t.tenant_id) as s:
        clave = {"c": str(uuid.uuid4()), "l": str(uuid.uuid4()), "ts": str(uuid.uuid4())}
        insertar_matriz(s, t.tenant_id, clave, {req: "bloqueante_duro"})
        s.execute(text("INSERT INTO modulo1.oc (tenant_id, clave_origen, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta) "
                       "VALUES (:t, 'OC-R', :c, :l, :ts, :d, :h)"), {"t": t.tenant_id, **clave, "d": VENCE + timedelta(days=10), "h": VENCE + timedelta(days=20)})
    ev = _post(cliente_api, t, "responsable_legajos", "evaluar_habilitacion", {"commitment_id": "OC-R", "sujetos_propuestos": [persona]})
    assert ev.status_code == 200
    _reloj(t, VENCE + timedelta(days=1))
    with tenant_session(t.tenant_id) as s:
        avisos = s.execute(text("SELECT count(*) FROM modulo1.aviso_revaluacion WHERE tenant_id = :t AND referencia_evaluacion = :r AND estado = 'abierto'"),
                           {"t": t.tenant_id, "r": ev.json()["referencia_evaluacion"]}).scalar()
    assert avisos == 1
