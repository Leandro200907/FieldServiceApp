"""A-07: política de revaluación (tabla 7.2) → avisos normalizados → outbox.

Escenario base: empresa + persona_A (universo de sup) + persona_B, matriz con apto
(persona, excepcionable) y ART (empresa), OC-1 activa con decisión D1 = [persona_A].
"""
from __future__ import annotations

import threading
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.comun.eventos import registrar_evento, registrar_evento_interno
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.core.incumplimiento_empresa import registrar_vencimientos_de_empresa
from app.core.orquestacion import decidir_habilitacion
from app.core.revaluacion import EVENTOS_FUENTE, EVENTOS_PRODUCIDOS, aplicar_politica
from app.db import tenant_session
from app.worker.outbox import PublicadorEnMemoria, drenar_outbox
from tests.test_orquestacion import (
    clave_de_matriz,
    insertar_definicion,
    insertar_documento,
    insertar_legajo,
    insertar_matriz,
    insertar_oc,
    sesion,  # noqa: F401
)
from tests.test_robustez import _en_paralelo

AHORA = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _base(s, t, *, persona_b: bool = True) -> dict:
    clave = clave_de_matriz()
    insertar_legajo(s, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(s, t.tenant_id, "persona_A", "persona")
    if persona_b:
        insertar_legajo(s, t.tenant_id, "persona_B", "persona")
    req_e = insertar_definicion(s, t.tenant_id, "ART", "empresa")
    req_p = insertar_definicion(s, t.tenant_id, "Apto", "persona")
    m1 = insertar_matriz(s, t.tenant_id, clave, {req_e: "bloqueante_duro", req_p: "excepcionable"})
    insertar_documento(s, t.tenant_id, "empresa_0001", req_e, date(2026, 1, 1), date(2026, 12, 31))
    insertar_documento(s, t.tenant_id, "persona_A", req_p, date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(s, t.tenant_id, "OC-1", clave, date(2026, 10, 1), date(2026, 10, 5))
    d1 = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, t.usuarios["responsable_legajos"])["referencia_evaluacion"]
    return {"clave": clave, "req_e": req_e, "req_p": req_p, "m1": m1, "d1": d1}


def _avisos(t, ref: str | None = None) -> list[dict]:
    with tenant_session(t.tenant_id) as s:
        q = "SELECT aviso_id, referencia_evaluacion, commitment_id, estado FROM modulo1.aviso_revaluacion"
        if ref:
            q += " WHERE referencia_evaluacion = :r"
        return [dict(f) for f in s.execute(text(q + " ORDER BY abierto_en"), {"r": ref}).mappings()]


def _causas(t, aviso_id: str) -> list[dict]:
    with tenant_session(t.tenant_id) as s:
        return [dict(f) for f in s.execute(text("SELECT evento_id, tipo_evento, entidad_tipo, entidad_id FROM modulo1.aviso_revaluacion_causa "
                                                 "WHERE aviso_id = :a ORDER BY registrada_en"), {"a": aviso_id}).mappings()]


def _outbox(t, tipo: str = "HabilitacionRequiereRevaluacion") -> list[dict]:
    with tenant_session(t.tenant_id) as s:
        return [dict(f) for f in s.execute(text("SELECT evento_id, tipo, payload, clave_dedup, version_contrato, procesado_en "
                                                 "FROM modulo1.outbox_events WHERE tipo = :tipo ORDER BY creado_en"), {"tipo": tipo}).mappings()]


def _cargar_declarado(cliente_api, t, sujeto: str, req: str, desde="2026-06-01", hasta="2027-06-01") -> str:
    """Nueva versión declarada por el comando real (sucede al vigente); lista para confirmar."""
    r = cliente_api.post("/v1/comandos/cargar_documento", json={"sujeto_id": sujeto, "requisito_definicion_id": req,
                         "vigente_desde": desde, "vigente_hasta": hasta, "estado_confirmacion": "declarado"},
                         headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    return r.json()["documento_id"]


def _eventos(t, tipo: str) -> int:
    with tenant_session(t.tenant_id) as s:
        return s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = :tipo"), {"tipo": tipo}).scalar()


# ============================================================ positivos (una fila de 7.2 cada uno)


def _espera_un_aviso(t, ref, tipo_evento, entidad_tipo):
    avisos = _avisos(t, ref)
    assert [a["estado"] for a in avisos] == ["abierto"]
    causas = _causas(t, str(avisos[0]["aviso_id"]))
    assert [(c["tipo_evento"], c["entidad_tipo"]) for c in causas] == [(tipo_evento, entidad_tipo)]
    ob = _outbox(t)
    assert len(ob) == 1 and ob[0]["clave_dedup"] == f"hrr:{ref}:{avisos[0]['aviso_id']}"
    p = ob[0]["payload"]
    assert p["version_contrato"] == "1.0" and p["tenant_id"] == t.tenant_id and p["referencia_evaluacion"] == ref
    assert p["commitment_id"] == "OC-1" and p["evento_causal"]["tipo"] == tipo_evento and p["evento_causal"]["evento_id"] == str(causas[0]["evento_id"])
    assert p["emitido_en"] and p["aviso_id"] == str(avisos[0]["aviso_id"])
    assert _eventos(t, "AvisoDeRevaluacionAbierto") == 1


def test_documento_verificado_marca_decisiones_que_proponen_al_sujeto(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.commit()
    doc = _cargar_declarado(cliente_api, t, "persona_A", e["req_p"])
    assert _avisos(t) == []  # DocumentoCargado (declarado) es negativo
    r = cliente_api.post("/v1/comandos/confirmar_documento", json={"documento_id": doc}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    _espera_un_aviso(t, e["d1"], "DocumentoVerificado", "documento")


def test_documento_verificado_de_empresa_marca_todas_las_decisiones(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    insertar_oc(sesion, t.tenant_id, "OC-2", e["clave"], date(2026, 10, 1), date(2026, 10, 5))
    insertar_documento(sesion, t.tenant_id, "persona_B", e["req_p"], date(2026, 1, 1), date(2026, 12, 31))
    d2 = decidir_habilitacion(sesion, t.tenant_id, "OC-2", ["persona_B"], AHORA, None)["referencia_evaluacion"]
    sesion.commit()
    doc = _cargar_declarado(cliente_api, t, "empresa_0001", e["req_e"])
    cliente_api.post("/v1/comandos/confirmar_documento", json={"documento_id": doc}, headers=t.headers("responsable_legajos"))
    assert {a["referencia_evaluacion"] for a in _avisos(t)} == {uuid.UUID(e["d1"]), uuid.UUID(d2)}
    assert len(_outbox(t)) == 2


def test_lote_revertido_marca_por_sujetos_del_lote(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.commit()
    lote = str(uuid.uuid4())
    h = t.headers("responsable_legajos")
    r = cliente_api.post("/v1/comandos/importar_lote", json={"lote_id": lote, "filas": [
        {"sujeto_id": "persona_A", "requisito_definicion_id": e["req_p"], "vigente_desde": "2026-06-01", "vigente_hasta": "2027-06-01"}]}, headers=h)
    assert r.status_code == 200, r.text
    assert _avisos(t) == []  # LoteAplicado + DocumentoCargado declarado: negativos
    assert cliente_api.post("/v1/comandos/revertir_lote", json={"lote_id": lote}, headers=h).status_code == 200
    _espera_un_aviso(t, e["d1"], "LoteRevertido", "lote_importacion")


def test_legajo_dado_de_baja_marca(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.commit()
    assert cliente_api.post("/v1/comandos/baja_de_sujeto", json={"sujeto_id": "persona_A"}, headers=t.headers("responsable_legajos")).status_code == 200
    _espera_un_aviso(t, e["d1"], "LegajoDadoDeBaja", "legajo")


def test_matriz_publicada_marca_solo_decisiones_bajo_la_version_cerrada(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    # otra OC de otra clave de matriz: no debe marcarse
    otra = clave_de_matriz()
    insertar_matriz(sesion, t.tenant_id, otra, {e["req_p"]: "excepcionable"})
    insertar_oc(sesion, t.tenant_id, "OC-otra", otra, date(2026, 10, 1), date(2026, 10, 5))
    decidir_habilitacion(sesion, t.tenant_id, "OC-otra", ["persona_A"], AHORA, None)
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    sesion.commit()
    body = {"cliente_id": e["clave"]["c"], "locacion_id": e["clave"]["l"], "tipo_servicio_id": e["clave"]["ts"],
            "vigente_desde": (hoy + timedelta(days=1)).isoformat(),
            "lineas": [{"requisito_definicion_id": e["req_p"], "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}]}
    r = cliente_api.post("/v1/comandos/publicar_version_de_matriz", json=body, headers=t.headers("configuracion"))
    assert r.status_code == 200, r.text
    _espera_un_aviso(t, e["d1"], "MatrizVersionPublicada", "matriz_requisitos")


def test_requisito_particular_marca_solo_su_commitment(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    insertar_oc(sesion, t.tenant_id, "OC-2", e["clave"], date(2026, 10, 1), date(2026, 10, 5))
    decidir_habilitacion(sesion, t.tenant_id, "OC-2", ["persona_A"], AHORA, None)
    sesion.commit()
    r = cliente_api.post("/v1/comandos/cargar_requisito_particular", json={
        "commitment_id": "OC-1", "requisito_definicion_id": e["req_p"], "clasificacion": "bloqueante_duro",
        "bloqueante_durante_ejecucion": True}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    _espera_un_aviso(t, e["d1"], "RequisitoParticularCargado", "requisito_particular")


def test_excepcion_ciclo_completo_marca_en_cada_transicion(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.execute(text("DELETE FROM modulo1.documento WHERE sujeto_id = 'persona_A'"))
    sesion.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                        "VALUES (:t, 'persona_A', :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "u": t.usuarios["supervisor"]})
    sesion.commit()
    sup = t.headers("supervisor")
    exc = cliente_api.post("/v1/comandos/otorgar_excepcion", json={"referencia_evaluacion": e["d1"], "sujeto_id": "persona_A",
                           "requisito_definicion_id": e["req_p"], "commitment_id": "OC-1", "motivo": "m"}, headers=sup)
    assert exc.status_code == 200, exc.text
    _espera_un_aviso(t, e["d1"], "ExcepcionOtorgada", "excepcion")
    # revocar: misma decisión, aviso ya abierto → segunda causa, sin outbox nuevo
    assert cliente_api.post("/v1/comandos/revocar_excepcion", json={"excepcion_id": exc.json()["excepcion_id"]}, headers=sup).status_code == 200
    avisos = _avisos(t, e["d1"])
    assert len(avisos) == 1 and len(_causas(t, str(avisos[0]["aviso_id"]))) == 2 and len(_outbox(t)) == 1


def test_constancia_general_marca_decisiones_del_cliente_que_proponen_al_sujeto(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.execute(text("UPDATE modulo1.linea_requisito SET clasificacion = 'bloqueante_duro' WHERE requisito_definicion_id = :r"), {"r": e["req_p"]})
    sesion.commit()
    r = cliente_api.post("/v1/comandos/registrar_constancia_del_cliente", json={
        "sujeto_id": "persona_A", "requisito_definicion_id": e["req_p"], "cliente_id": e["clave"]["c"], "evidencia": "mail"},
        headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    _espera_un_aviso(t, e["d1"], "ConstanciaRegistrada", "constancia_cliente")


def test_vencimientos_del_reloj_marcan(tenant_de_prueba, sesion):
    from app.worker.procesos_reloj import vencer_excepciones_y_constancias

    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.execute(text("INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, commitment_id, "
                        "otorgada_por, motivo, vigencia) VALUES (:t, :r, 'persona_A', :q, 'OC-1', 'sup', 'm', '2026-01-01')"),
                   {"t": t.tenant_id, "r": e["d1"], "q": e["req_p"]})
    sesion.commit()
    with tenant_session(t.tenant_id) as s:
        vencer_excepciones_y_constancias(s, t.tenant_id, ahora_utc())
    _espera_un_aviso(t, e["d1"], "ExcepcionVencida", "excepcion")


# ============================================================ negativos (una fila de 7.2 cada uno)


@pytest.mark.parametrize("tipo", [
    "DocumentoCargado", "DocumentoRechazado", "DocumentoSucedido", "AcreditacionDeCompetenciaRegistrada", "InduccionRegistrada",
    "LoteAplicado", "LegajoCreado", "SupervisorAsignado", "SupervisorReasignado", "DefinicionDeRequisitoDadaDeAlta",
    "DefinicionDeRequisitoDadaDeBaja", "EvaluacionDeHabilitacionRealizada", "TareaDeRegularizacionCreada", "CustodiaCorregida",
    "ConstanciaReemplazada", "AlertaDeVencimientoAbierta", "AlertaPausada", "AlertaResuelta", "AlertaEscalada", "ArchivoPurgado",
    "AvisoDeRevaluacionAbierto", "AvisoDeRevaluacionCerrado", "CumplimientoEmpresaAfectado", "CumplimientoEmpresaRegularizado",
])
def test_eventos_excluidos_por_7_2_no_marcan_nada(tenant_de_prueba, sesion, tipo):
    t = tenant_de_prueba
    e = _base(sesion, t)
    assert tipo not in EVENTOS_FUENTE
    payload = {"sujeto_id": "persona_A", "documento_id": str(uuid.uuid4()), "commitment_id": "OC-1", "referencia_evaluacion": e["d1"],
               "aviso_id": str(uuid.uuid4()), "lote_id": str(uuid.uuid4()), "recurso_id": "persona_A"}
    registrar_evento(sesion, t.tenant_id, tipo, payload, None)
    sesion.commit()
    assert _avisos(t) == [] and _outbox(t) == [] and _outbox(t, "CumplimientoEmpresaAfectado") == []
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.politica_evento_procesado")).scalar() == 0


def test_despachador_no_recursa_al_abrir_o_cerrar_avisos(tenant_de_prueba, sesion):
    """Los eventos producidos por la política se registran por la vía interna y no están en
    el mapa: registrar uno a mano tampoco dispara nada."""
    t = tenant_de_prueba
    e = _base(sesion, t)
    assert not (set(EVENTOS_FUENTE) & EVENTOS_PRODUCIDOS)
    for tipo in EVENTOS_PRODUCIDOS:
        registrar_evento_interno(sesion, t.tenant_id, tipo, {"referencia_evaluacion": e["d1"]}, None)
        registrar_evento(sesion, t.tenant_id, tipo, {"referencia_evaluacion": e["d1"]}, None)
    sesion.commit()
    assert _avisos(t) == [] and _outbox(t) == []


# ============================================================ custodia condicional


def _custodia_cambiada(cliente_api, t, recurso: str):
    return cliente_api.post("/v1/comandos/cambiar_custodia", json={"recurso_id": recurso, "tipo_recurso": "vehiculo",
                            "custodio_id": "persona_A", "desde": "2026-09-19"}, headers=t.headers("supervisor"))


def test_custodia_cambiada_no_marca_decision_con_sujetos_explicitos(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    insertar_legajo(sesion, t.tenant_id, "vehiculo_V", "vehiculo")
    d = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_A", "vehiculo_V"], AHORA, None)  # explícito
    sesion.commit()
    assert d["origen_sujetos"] == "explicito"
    assert _custodia_cambiada(cliente_api, t, "vehiculo_V").status_code == 200
    assert _avisos(t) == [] and _outbox(t) == []


def test_custodia_cambiada_marca_decision_con_custodia_por_defecto(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    insertar_legajo(sesion, t.tenant_id, "vehiculo_V", "vehiculo")
    d = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_A", "vehiculo_V"], AHORA, None, origen_sujetos="custodia_por_defecto")
    sesion.commit()
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT origen_sujetos FROM modulo1.evaluacion_habilitacion WHERE referencia_evaluacion = :r"),
                         {"r": d["referencia_evaluacion"]}).scalar() == "custodia_por_defecto"
    assert d["snapshot"]["origen_sujetos"] == "custodia_por_defecto"
    assert _custodia_cambiada(cliente_api, t, "vehiculo_V").status_code == 200
    _espera_un_aviso(t, d["referencia_evaluacion"], "CustodiaCambiada", "periodo_custodia")


def test_origen_sujetos_no_es_falsificable_desde_la_api(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    _base(sesion, t)
    sesion.commit()
    esquema = cliente_api.get("/openapi.json").json()["components"]["schemas"]["EvaluarHabilitacionBody"]
    assert "origen_sujetos" not in esquema["properties"]
    r = cliente_api.post("/v1/comandos/evaluar_habilitacion", json={"commitment_id": "OC-1", "sujetos_propuestos": ["persona_A"],
                         "origen_sujetos": "custodia_por_defecto"}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200 and r.json()["origen_sujetos"] == "explicito"
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT origen_sujetos FROM modulo1.evaluacion_habilitacion WHERE referencia_evaluacion = :r"),
                         {"r": r.json()["referencia_evaluacion"]}).scalar() == "explicito"


# ============================================================ compromiso: cancelación transaccional


def test_cancelar_oc_abre_un_aviso_y_un_outbox_con_tipo_cambio(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.commit()
    r = cliente_api.post("/v1/comandos/cancelar_oc", json={"clave_origen": "OC-1"}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200 and r.json()["eventos"] == ["CompromisoCancelado"]
    _espera_un_aviso(t, e["d1"], "CompromisoCancelado", "oc")
    assert _outbox(t)[0]["payload"]["tipo_cambio"] == "cancelacion"  # el consumidor INVALIDA, no crea decisión


def test_cancelar_oc_con_rollback_no_deja_aviso_ni_outbox(tenant_de_prueba, sesion):
    from app.api.errores import ErrorDeDominio
    from app.auth.identidad import Identidad, Rol
    from app.modules.oc.servicio import cancelar_oc

    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.commit()
    ident = Identidad(t.tenant_id, t.usuarios["responsable_legajos"], frozenset({Rol.RESPONSABLE_LEGAJOS}))
    with pytest.raises(ErrorDeDominio):
        with tenant_session(t.tenant_id) as s:
            r = cancelar_oc(s, ident, None, "OC-1")
            assert r["eventos"] == ["CompromisoCancelado"]
            assert len(s.execute(text("SELECT 1 FROM modulo1.aviso_revaluacion")).all()) == 1  # dentro de la tx sí
            raise ErrorDeDominio("algo falló después del cambio")
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT estado FROM modulo1.oc WHERE clave_origen = 'OC-1'")).scalar() == "activo"
    assert _avisos(t) == [] and _outbox(t) == [] and _eventos(t, "CompromisoCancelado") == 0
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.aviso_revaluacion_causa")).scalar() == 0
        assert s.execute(text("SELECT count(*) FROM modulo1.politica_evento_procesado")).scalar() == 0


# ============================================================ idempotencia por evento causal y coalescing


def test_mismo_evento_id_con_aviso_abierto_una_causa_y_tras_cerrar_no_reabre(tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    ev = registrar_evento(sesion, t.tenant_id, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}, None)
    sesion.commit()
    aviso = _avisos(t, e["d1"])[0]
    # replay del mismo evento con el aviso abierto → nada nuevo
    with tenant_session(t.tenant_id) as s:
        assert aplicar_politica(s, t.tenant_id, ev, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}) == []
    assert len(_causas(t, str(aviso["aviso_id"]))) == 1 and len(_outbox(t)) == 1
    # decisión nueva cierra el aviso; replay del evento antiguo NO lo reabre
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.legajo SET dado_de_baja_en = NULL WHERE sujeto_id = 'persona_A'"))
        d2 = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, None)
    assert d2["avisos_cerrados"] == [str(aviso["aviso_id"])]
    with tenant_session(t.tenant_id) as s:
        assert aplicar_politica(s, t.tenant_id, ev, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}) == []
    assert [a["estado"] for a in _avisos(t)] == ["cerrado"] and len(_outbox(t)) == 1


def test_dos_eventos_distintos_misma_evaluacion_un_aviso_dos_causas_un_outbox(tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    registrar_evento(sesion, t.tenant_id, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}, None)
    registrar_evento(sesion, t.tenant_id, "RequisitoParticularCargado", {"commitment_id": "OC-1", "requisito_particular_id": "rp"}, None)
    sesion.commit()
    avisos = _avisos(t, e["d1"])
    assert len(avisos) == 1 and len(_causas(t, str(avisos[0]["aviso_id"]))) == 2 and len(_outbox(t)) == 1


def test_dos_aperturas_concurrentes_un_aviso_un_outbox(tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.commit()

    def marcar():
        with tenant_session(t.tenant_id) as s:
            registrar_evento(s, t.tenant_id, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}, None)

    salidas = _en_paralelo([marcar, marcar])
    assert all(x is None for _, x in salidas), [str(x) for _, x in salidas if x]
    avisos = _avisos(t, e["d1"])
    assert len(avisos) == 1 and len(_causas(t, str(avisos[0]["aviso_id"]))) == 2 and len(_outbox(t)) == 1


def test_rollback_del_productor_no_deja_nada(tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    sesion.commit()
    with pytest.raises(RuntimeError):
        with tenant_session(t.tenant_id) as s:
            registrar_evento(s, t.tenant_id, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}, None)
            raise RuntimeError("falla después del evento")
    with tenant_session(t.tenant_id) as s:
        for tabla in ("event_log", "politica_evento_procesado", "aviso_revaluacion", "aviso_revaluacion_causa", "outbox_events"):
            n = s.execute(text(f"SELECT count(*) FROM modulo1.{tabla} WHERE {'tipo = :x' if tabla in ('event_log', 'outbox_events') else 'true'}"),
                          {"x": "LegajoDadoDeBaja" if tabla == "event_log" else "HabilitacionRequiereRevaluacion"}).scalar()
            assert n == 0, tabla


# ============================================================ cierre por decisión nueva


def test_decision_nueva_cierra_solo_avisos_de_su_commitment_y_rollback_los_conserva(tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    insertar_oc(sesion, t.tenant_id, "OC-2", e["clave"], date(2026, 10, 1), date(2026, 10, 5))
    d_otra = decidir_habilitacion(sesion, t.tenant_id, "OC-2", ["persona_A"], AHORA, None)["referencia_evaluacion"]
    registrar_evento(sesion, t.tenant_id, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}, None)  # marca D1 y d_otra
    sesion.execute(text("UPDATE modulo1.legajo SET dado_de_baja_en = NULL WHERE sujeto_id = 'persona_A'"))
    sesion.commit()
    assert {a["estado"] for a in _avisos(t)} == {"abierto"} and len(_avisos(t)) == 2
    # rollback de la decisión 2 → el aviso original sigue abierto
    with pytest.raises(RuntimeError):
        with tenant_session(t.tenant_id) as s:
            r = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, None)
            assert len(r["avisos_cerrados"]) == 1
            raise RuntimeError("rollback")
    assert [a["estado"] for a in _avisos(t, e["d1"])] == ["abierto"] and _eventos(t, "AvisoDeRevaluacionCerrado") == 0
    # decisión 2 real: cierra el de OC-1, no el de OC-2
    with tenant_session(t.tenant_id) as s:
        r = decidir_habilitacion(s, t.tenant_id, "OC-1", ["persona_A"], AHORA, None)
    assert [a["estado"] for a in _avisos(t, e["d1"])] == ["cerrado"]
    assert [a["estado"] for a in _avisos(t, d_otra)] == ["abierto"]
    assert _eventos(t, "AvisoDeRevaluacionCerrado") == 1 and _avisos(t, r["referencia_evaluacion"]) == []


# ============================================================ incumplimiento de empresa


def test_incumplimiento_empresa_abre_suma_regulariza_parcial_y_cierra(cliente_api, tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    req_b = insertar_definicion(sesion, t.tenant_id, "Seguro RC", "empresa")
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    # A (ART) vence ayer; B (Seguro RC) vence anteayer
    sesion.execute(text("UPDATE modulo1.documento SET vigente_hasta = :h WHERE sujeto_id = 'empresa_0001'"), {"h": hoy - timedelta(days=1)})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_b, date(2026, 1, 1), hoy - timedelta(days=2))
    r1 = registrar_vencimientos_de_empresa(sesion, t.tenant_id, hoy)
    assert r1["aviso_abierto"] and r1["causas_nuevas"] == 2
    r2 = registrar_vencimientos_de_empresa(sesion, t.tenant_id, hoy)  # segunda vuelta: nada nuevo, sin outbox nuevo
    assert not r2["aviso_abierto"] and r2["causas_nuevas"] == 0
    sesion.commit()
    cea = _outbox(t, "CumplimientoEmpresaAfectado")
    assert len(cea) == 1 and cea[0]["clave_dedup"] == f"cea:{r1['aviso_id']}"
    assert "causas" not in cea[0]["payload"] and cea[0]["payload"]["aviso_id"] == r1["aviso_id"]  # flaco
    # marca interna de la decisión vigente, sin HRR a outbox
    assert len(_avisos(t, e["d1"])) == 1 and _outbox(t) == []
    estado = cliente_api.get("/v1/consultas/incumplimiento_empresa", headers=t.headers("responsable_legajos")).json()["aviso"]
    assert estado["estado"] == "abierto" and set(estado["causas_activas"]) == {e["req_e"], req_b}
    # regulariza A: el aviso sigue abierto con B
    doc_a = _cargar_declarado(cliente_api, t, "empresa_0001", e["req_e"], hoy.isoformat(), (hoy + timedelta(days=365)).isoformat())
    assert cliente_api.post("/v1/comandos/confirmar_documento", json={"documento_id": doc_a}, headers=t.headers("responsable_legajos")).status_code == 200
    estado = cliente_api.get("/v1/consultas/incumplimiento_empresa", headers=t.headers("responsable_legajos")).json()["aviso"]
    assert estado["estado"] == "abierto" and estado["causas_activas"] == [req_b]
    assert {c["estado"] for c in estado["causas"]} == {"activa", "regularizada"}
    # regulariza B: recién ahora cierra
    doc_b = _cargar_declarado(cliente_api, t, "empresa_0001", req_b, hoy.isoformat(), (hoy + timedelta(days=365)).isoformat())
    assert cliente_api.post("/v1/comandos/confirmar_documento", json={"documento_id": doc_b}, headers=t.headers("responsable_legajos")).status_code == 200
    estado = cliente_api.get("/v1/consultas/incumplimiento_empresa", headers=t.headers("responsable_legajos")).json()["aviso"]
    assert estado["estado"] == "regularizado" and estado["causas_activas"] == []
    assert _eventos(t, "CumplimientoEmpresaRegularizado") == 1 and len(_outbox(t, "CumplimientoEmpresaAfectado")) == 1


def test_regularizacion_concurrente_de_a_y_b_cierra_exactamente_una_vez(tenant_de_prueba, sesion):
    from app.core.incumplimiento_empresa import reevaluar_causas

    t = tenant_de_prueba
    e = _base(sesion, t)
    req_b = insertar_definicion(sesion, t.tenant_id, "Seguro RC", "empresa")
    hoy = hoy_del_tenant(sesion, t.tenant_id)
    sesion.execute(text("UPDATE modulo1.documento SET vigente_hasta = :h WHERE sujeto_id = 'empresa_0001'"), {"h": hoy - timedelta(days=1)})
    insertar_documento(sesion, t.tenant_id, "empresa_0001", req_b, date(2026, 1, 1), hoy - timedelta(days=2))
    registrar_vencimientos_de_empresa(sesion, t.tenant_id, hoy)
    # ambos requisitos quedan cubiertos "a la vez" (documentos nuevos vigentes)
    sesion.execute(text("UPDATE modulo1.documento SET vigente_hasta = :h WHERE sujeto_id = 'empresa_0001'"), {"h": hoy + timedelta(days=100)})
    sesion.commit()

    def reevaluar():
        with tenant_session(t.tenant_id) as s:
            return reevaluar_causas(s, t.tenant_id, hoy)

    salidas = _en_paralelo([reevaluar, reevaluar])
    assert all(x is None for _, x in salidas)
    assert sum(1 for r, _ in salidas if r["cerrado"]) == 1
    assert _eventos(t, "CumplimientoEmpresaRegularizado") == 1
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.aviso_incumplimiento_empresa_causa WHERE estado = 'activa'")).scalar() == 0


# ============================================================ publicación con dos workers


def test_drenaje_con_dos_workers_publica_cada_evento_una_vez(tenant_de_prueba, sesion):
    t = tenant_de_prueba
    e = _base(sesion, t)
    for i in range(6):  # 6 OCs con decisión → 6 HRR distintos
        insertar_oc(sesion, t.tenant_id, f"OC-{i+10}", e["clave"], date(2026, 10, 1), date(2026, 10, 5))
        decidir_habilitacion(sesion, t.tenant_id, f"OC-{i+10}", ["persona_A"], AHORA, None)
    registrar_evento(sesion, t.tenant_id, "LegajoDadoDeBaja", {"sujeto_id": "persona_A"}, None)
    sesion.commit()
    assert len(_outbox(t)) == 7
    pub = PublicadorEnMemoria()
    barrera = threading.Barrier(2)

    def worker():
        barrera.wait(timeout=10)
        total = 0
        for _ in range(3):
            with tenant_session(t.tenant_id) as s:
                total += drenar_outbox(s, t.tenant_id, pub, lote=3)
        return total

    salidas = _en_paralelo([worker, worker])
    assert all(x is None for _, x in salidas)
    ids = [ev_id for _, _, ev_id in pub.eventos]
    assert len(ids) == 7 and len(set(ids)) == 7  # cada evento exactamente una vez (SKIP LOCKED + procesado_en)
    assert all(o["procesado_en"] is not None for o in _outbox(t))
    assert all(p["version_contrato"] == "1.0" for _, p, _ in pub.eventos)
