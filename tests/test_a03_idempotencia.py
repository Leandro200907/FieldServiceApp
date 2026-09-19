"""A-03 de la auditoría: idempotencia con reserva atómica antes del efecto.

Los tests usan el primitivo `ejecutar_idempotente` con un efecto instrumentado (cuenta
ejecuciones y escribe una fila real) y también la API HTTP con hilos reales.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.api.errores import Conflicto, ErrorDeDominio
from app.comun.idempotencia import ejecutar_idempotente, fingerprint_de
from app.db import tenant_session
from tests.test_robustez import _en_paralelo


def _efecto_instrumentado(tenant_id: str, demora: float = 0.0):
    ejecuciones = {"n": 0}

    def efecto(s):
        ejecuciones["n"] += 1
        if demora:
            time.sleep(demora)
        s.execute(text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) "
                       "VALUES (:t, :sj, 'persona', :sj)"), {"t": tenant_id, "sj": f"p_{uuid.uuid4().hex[:8]}"})
        return {"ok": True, "n": ejecuciones["n"]}

    return efecto, ejecuciones


def _fila(tenant_id: str, clave: str) -> dict | None:
    with tenant_session(tenant_id) as s:
        f = s.execute(text("SELECT estado, fingerprint, resultado, reservada_hasta FROM modulo1.idempotency_keys "
                           "WHERE idempotency_key = :k"), {"k": clave}).mappings().first()
        return dict(f) if f else None


def _legajos(tenant_id: str) -> int:
    with tenant_session(tenant_id) as s:
        return s.execute(text("SELECT count(*) FROM modulo1.legajo")).scalar()


def test_dos_solicitudes_simultaneas_misma_clave_mismo_fingerprint_ejecutan_una_sola_vez(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t, demora=0.5)
    fp = fingerprint_de("POST", "/x", {"a": 1})
    salidas = _en_paralelo([lambda: ejecutar_idempotente(t, "k1", fp, efecto)] * 2)
    oks = [r for r, e in salidas if e is None]
    errores = [e for _, e in salidas if e is not None]
    assert len(oks) == 1 and len(errores) == 1 and isinstance(errores[0], Conflicto)
    assert errores[0].codigo == "operacion_en_proceso"
    assert ejecuciones["n"] == 1 and _legajos(t) == 1
    assert _fila(t, "k1")["estado"] == "completada"


def test_misma_clave_con_body_o_ruta_distintos_es_conflicto(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t)
    ejecutar_idempotente(t, "k2", fingerprint_de("POST", "/x", {"a": 1}), efecto)
    with pytest.raises(Conflicto) as e1:
        ejecutar_idempotente(t, "k2", fingerprint_de("POST", "/x", {"a": 2}), efecto)
    with pytest.raises(Conflicto) as e2:
        ejecutar_idempotente(t, "k2", fingerprint_de("POST", "/y", {"a": 1}), efecto)
    assert e1.value.codigo == e2.value.codigo == "clave_idempotencia_reutilizada"
    assert ejecuciones["n"] == 1


def test_repeticion_posterior_es_replay_exacto_sin_reejecutar(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t)
    fp = fingerprint_de("POST", "/x", {"a": 1})
    r1 = ejecutar_idempotente(t, "k3", fp, efecto)
    r2 = ejecutar_idempotente(t, "k3", fp, efecto)
    r3 = ejecutar_idempotente(t, "k3", fp, efecto)
    assert r1 == r2 == r3 and ejecuciones["n"] == 1 and _legajos(t) == 1


def test_reserva_en_proceso_es_visible_y_bloquea_a_otros(tenant_de_prueba):
    """Mientras el efecto corre, la reserva ya está commiteada como `en_proceso`."""
    t = tenant_de_prueba.tenant_id
    visto = {}
    listo = threading.Event()

    def efecto(s):
        visto["fila"] = _fila(t, "k4")  # desde otra sesión: solo ve lo commiteado
        try:
            ejecutar_idempotente(t, "k4", fp, lambda s2: {"no": "debería"})
        except Conflicto as e:
            visto["conflicto"] = e.codigo
        listo.set()
        return {"ok": True}

    fp = fingerprint_de("POST", "/x", {})
    ejecutar_idempotente(t, "k4", fp, efecto)
    assert visto["fila"]["estado"] == "en_proceso" and visto["fila"]["resultado"] is None
    assert visto["conflicto"] == "operacion_en_proceso"
    assert _fila(t, "k4")["estado"] == "completada"


def test_reserva_vencida_se_recupera_y_reserva_fallida_se_libera(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    fp = fingerprint_de("POST", "/x", {})
    # 1) reserva huérfana (proceso caído): en_proceso con lease vencido → se retoma
    with tenant_session(t) as s:
        s.execute(text("INSERT INTO modulo1.idempotency_keys (tenant_id, idempotency_key, estado, fingerprint, expira_en, "
                       "reservada_en, reservada_hasta) VALUES (:t, 'k5', 'en_proceso', :fp, now() + interval '1 day', "
                       "now() - interval '10 minutes', now() - interval '5 minutes')"), {"t": t, "fp": fp})
    efecto, ejecuciones = _efecto_instrumentado(t)
    r = ejecutar_idempotente(t, "k5", fp, efecto)
    assert r["ok"] and ejecuciones["n"] == 1 and _fila(t, "k5")["estado"] == "completada"
    # 2) el efecto falla → la reserva se libera y el siguiente intento ejecuta
    def explota(s):
        raise ErrorDeDominio("no")
    with pytest.raises(ErrorDeDominio):
        ejecutar_idempotente(t, "k6", fp, explota)
    assert _fila(t, "k6") is None
    r = ejecutar_idempotente(t, "k6", fp, efecto)
    assert r["ok"] and ejecuciones["n"] == 2
    # 3) una reserva vencida con OTRO fingerprint también se retoma (la anterior nunca terminó)
    with tenant_session(t) as s:
        s.execute(text("UPDATE modulo1.idempotency_keys SET estado = 'en_proceso', resultado = NULL, fingerprint = 'otro', "
                       "reservada_hasta = now() - interval '1 minute' WHERE idempotency_key = 'k6'"))
    assert ejecutar_idempotente(t, "k6", fp, efecto)["ok"] and ejecuciones["n"] == 3


def test_http_dos_requests_simultaneos_no_ejecutan_dos_veces(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    body = {"tipo_sujeto": "persona", "identificador_natural": "DNI-77"}
    h = t.headers("responsable_legajos", idempotency_key="k-http")

    def pedir():
        return cliente_api.post("/v1/comandos/alta_de_sujeto", json=body, headers=h)

    salidas = _en_paralelo([pedir, pedir])
    codigos = sorted(r.status_code for r, _ in salidas)
    assert codigos == [200, 409], codigos
    # replay posterior: mismo resultado; otro body con la misma clave: 409
    r = cliente_api.post("/v1/comandos/alta_de_sujeto", json=body, headers=h)
    ok = next(r for r, _ in salidas if r.status_code == 200)
    assert r.status_code == 200 and r.json() == ok.json()
    otro = cliente_api.post("/v1/comandos/alta_de_sujeto", json={**body, "identificador_natural": "DNI-78"}, headers=h)
    assert otro.status_code == 409 and otro.json()["error"]["codigo"] == "clave_idempotencia_reutilizada"
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.legajo")).scalar() == 1


def test_lote_prevalece_lote_id_sobre_header(cliente_api, tenant_de_prueba):
    """ImportarLote: la clave es el lote_id del body (regla 6 del brief); dos requests con
    distinto header y mismo lote_id son la misma operación."""
    from tests.test_comandos_legajos import _alta_def, _alta_persona

    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    persona = _alta_persona(cliente_api, t, "L-1")
    lote = str(uuid.uuid4())
    body = {"lote_id": lote, "origen": "planilla", "filas": [
        {"sujeto_id": persona, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"}]}
    r1 = cliente_api.post("/v1/comandos/importar_lote", json=body, headers=t.headers("responsable_legajos", idempotency_key="h1"))
    r2 = cliente_api.post("/v1/comandos/importar_lote", json=body, headers=t.headers("responsable_legajos", idempotency_key="h2"))
    assert r1.status_code == 200 and r2.status_code == 200 and r1.json() == r2.json()
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.lote_importacion")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'LoteAplicado'")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM modulo1.documento")).scalar() == 1
