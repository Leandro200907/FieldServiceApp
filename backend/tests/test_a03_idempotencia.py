"""A-03 de la auditoría (versión corregida): idempotencia con reserva atómica, ámbito por
actor, fingerprint inmutable y exclusión real durante el efecto (FOR UPDATE NOWAIT).

Los tests usan el primitivo `ejecutar_idempotente` con un efecto instrumentado (cuenta
ejecuciones de negocio y escribe una fila real) y también la API HTTP con hilos reales.
"""
from __future__ import annotations

import threading
import time
import uuid

import pytest
from sqlalchemy import text

from app.api.errores import Conflicto, ErrorDeDominio
from app.comun.idempotencia import ejecutar_idempotente, fingerprint_de
from app.db import tenant_session
from tests.test_orquestacion import sesion  # noqa: F401
from tests.test_robustez import _en_paralelo

ACTOR = "actor-1"


def _efecto_instrumentado(tenant_id: str, demora: float = 0.0, antes_de_escribir=None):
    ejecuciones = {"n": 0}

    def efecto(s):
        ejecuciones["n"] += 1
        if antes_de_escribir:
            antes_de_escribir()
        if demora:
            time.sleep(demora)
        s.execute(text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) "
                       "VALUES (:t, :sj, 'persona', :sj)"), {"t": tenant_id, "sj": f"p_{uuid.uuid4().hex[:8]}"})
        return {"ok": True, "n": ejecuciones["n"]}

    return efecto, ejecuciones


def _fila(tenant_id: str, clave: str, actor: str = ACTOR) -> dict | None:
    with tenant_session(tenant_id) as s:
        f = s.execute(text("SELECT estado, fingerprint, resultado, reservation_token, reservada_hasta "
                           "FROM modulo1.idempotency_keys WHERE idempotency_key = :k AND actor_id = :a"),
                      {"k": clave, "a": actor}).mappings().first()
        return dict(f) if f else None


def _legajos(tenant_id: str) -> int:
    with tenant_session(tenant_id) as s:
        return s.execute(text("SELECT count(*) FROM modulo1.legajo")).scalar()


FP = fingerprint_de("POST", "/x", {"a": 1})


def _run(t, clave, efecto, fp=FP, actor=ACTOR):
    return ejecutar_idempotente(t, actor, clave, fp, efecto)


# ------------------------------------------------------------------ concurrencia


def test_dos_simultaneas_misma_clave_mismo_fingerprint_efecto_una_vez(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t, demora=0.5)
    salidas = _en_paralelo([lambda: _run(t, "k1", efecto)] * 2)
    oks = [r for r, e in salidas if e is None]
    errores = [e for _, e in salidas if e is not None]
    assert len(oks) == 1 and len(errores) == 1 and isinstance(errores[0], Conflicto)
    assert errores[0].codigo == "operacion_en_proceso"
    assert ejecuciones["n"] == 1 and _legajos(t) == 1  # contador del efecto, no solo la fila
    assert _fila(t, "k1")["estado"] == "completada"


def test_1_ejecucion_mas_larga_que_reservada_hasta_y_la_segunda_no_ejecuta(tenant_de_prueba, monkeypatch):
    """El vencimiento informativo de la reserva NO habilita un segundo efecto: mientras el
    primero sostiene el lock de fila, el segundo recibe 409 y no toca nada. Se reserva con
    duración 0 (vencida desde el inicio) y se reintenta desde otro hilo en pleno efecto."""
    from app.comun import idempotencia as mod

    monkeypatch.setattr(mod, "RESERVA_SEGUNDOS", 0)
    t = tenant_de_prueba.tenant_id
    segundo = {}
    otro_efecto, otras = _efecto_instrumentado(t)

    def reintentar_en_paralelo():
        assert _fila(t, "k-largo")["estado"] == "en_proceso"
        time.sleep(0.2)  # la reserva ya está vencida (duración 0)

        def intento():
            try:
                _run(t, "k-largo", otro_efecto)
            except Conflicto as e:
                segundo["codigo"] = e.codigo

        hilo = threading.Thread(target=intento)
        hilo.start()
        hilo.join(timeout=20)
        segundo["ejecuciones"] = otras["n"]

    efecto, ejecuciones = _efecto_instrumentado(t, antes_de_escribir=reintentar_en_paralelo)
    r = _run(t, "k-largo", efecto)
    assert r["ok"] and ejecuciones["n"] == 1
    assert segundo == {"codigo": "operacion_en_proceso", "ejecuciones": 0}
    assert _legajos(t) == 1 and _fila(t, "k-largo")["estado"] == "completada"


# ------------------------------------------------------------------ fingerprint inmutable


def test_misma_clave_con_body_o_ruta_distintos_es_conflicto(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t)
    _run(t, "k2", efecto)
    for fp in (fingerprint_de("POST", "/x", {"a": 2}), fingerprint_de("POST", "/y", {"a": 1})):
        with pytest.raises(Conflicto) as e:
            _run(t, "k2", efecto, fp=fp)
        assert e.value.codigo == "clave_idempotencia_reutilizada"
    assert ejecuciones["n"] == 1


def test_2_clave_vencida_o_fallida_con_fingerprint_distinto_es_409(tenant_de_prueba):
    """Ni el vencimiento de la reserva ni el fallo del efecto permiten asociar la clave a
    otra operación: el fingerprint original se conserva."""
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t)
    with tenant_session(t) as s:  # reserva huérfana y vencida, fingerprint FP
        s.execute(text("INSERT INTO modulo1.idempotency_keys (tenant_id, actor_id, idempotency_key, estado, fingerprint, "
                       "reservation_token, expira_en, reservada_en, reservada_hasta) VALUES (:t, :a, 'k-h', 'en_proceso', :fp, "
                       ":tok, now() + interval '1 day', now() - interval '10 minutes', now() - interval '5 minutes')"),
                  {"t": t, "a": ACTOR, "fp": FP, "tok": uuid.uuid4()})
    with pytest.raises(Conflicto) as e:
        _run(t, "k-h", efecto, fp=fingerprint_de("POST", "/otra", {}))
    assert e.value.codigo == "clave_idempotencia_reutilizada" and ejecuciones["n"] == 0
    assert _fila(t, "k-h")["fingerprint"] == FP  # intacto
    # con el fingerprint original sí se recupera
    assert _run(t, "k-h", efecto)["ok"] and ejecuciones["n"] == 1
    # y después de completada, otro fingerprint sigue siendo 409
    with pytest.raises(Conflicto):
        _run(t, "k-h", efecto, fp=fingerprint_de("POST", "/otra", {}))


# ------------------------------------------------------------------ recuperación y tokens


def test_repeticion_posterior_es_replay_exacto_sin_reejecutar(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t)
    r1, r2, r3 = (_run(t, "k3", efecto) for _ in range(3))
    assert r1 == r2 == r3 and ejecuciones["n"] == 1 and _legajos(t) == 1


def test_reserva_en_proceso_es_visible_y_bloquea_a_otros(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    visto = {}

    def dentro():
        visto["fila"] = _fila(t, "k4")  # desde otra sesión: solo ve lo commiteado
        try:
            _run(t, "k4", lambda s2: {"no": "debería"})
        except Conflicto as e:
            visto["conflicto"] = e.codigo

    efecto, _ = _efecto_instrumentado(t, antes_de_escribir=dentro)
    _run(t, "k4", efecto)
    assert visto["fila"]["estado"] == "en_proceso" and visto["fila"]["resultado"] is None
    assert visto["conflicto"] == "operacion_en_proceso"
    assert _fila(t, "k4")["estado"] == "completada" and _fila(t, "k4")["reservation_token"] is None


def test_3_propietario_viejo_no_consolida_tras_recuperacion(tenant_de_prueba):
    """Reserva huérfana con token T0. Otra ejecución la recupera (token nuevo) y termina.
    Un intento de consolidar con T0 no afecta ninguna fila."""
    t = tenant_de_prueba.tenant_id
    t0 = uuid.uuid4()
    with tenant_session(t) as s:
        s.execute(text("INSERT INTO modulo1.idempotency_keys (tenant_id, actor_id, idempotency_key, estado, fingerprint, "
                       "reservation_token, expira_en, reservada_en, reservada_hasta) VALUES (:t, :a, 'k-t', 'en_proceso', :fp, "
                       ":tok, now() + interval '1 day', now(), now() + interval '2 minutes')"),
                  {"t": t, "a": ACTOR, "fp": FP, "tok": t0})
    efecto, ejecuciones = _efecto_instrumentado(t)
    r = _run(t, "k-t", efecto)  # lock libre → recuperación con token nuevo
    assert r["ok"] and _fila(t, "k-t")["estado"] == "completada"
    with tenant_session(t) as s:
        afectadas = s.execute(text("UPDATE modulo1.idempotency_keys SET estado = 'completada', resultado = '{\"viejo\": 1}' "
                                   "WHERE idempotency_key = 'k-t' AND estado = 'en_proceso' AND reservation_token = :tok"),
                              {"tok": t0}).rowcount
    assert afectadas == 0 and _fila(t, "k-t")["resultado"] == r


def test_4_caida_despues_de_reservar_y_antes_del_efecto_reintento_seguro(tenant_de_prueba):
    """Tx A commiteó la reserva; el proceso muere antes de Tx B. Reintento con el mismo
    fingerprint: recupera y ejecuta exactamente una vez."""
    from app.comun import idempotencia as mod

    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t)
    original = mod._abrir_por_defecto
    aperturas = {"n": 0}

    def abrir_y_morir_en_tx_b(tenant_id):
        aperturas["n"] += 1
        if aperturas["n"] == 2:  # Tx A ya commiteó la reserva; el proceso muere antes de Tx B
            raise RuntimeError("proceso caído después de reservar")
        return original(tenant_id)

    mod._abrir_por_defecto = abrir_y_morir_en_tx_b
    try:
        with pytest.raises(RuntimeError):
            _run(t, "k-c1", efecto)
    finally:
        mod._abrir_por_defecto = original
    assert _fila(t, "k-c1")["estado"] == "en_proceso" and ejecuciones["n"] == 0
    assert _run(t, "k-c1", efecto)["ok"] and ejecuciones["n"] == 1 and _legajos(t) == 1


def test_5_caida_dentro_de_la_transaccion_del_efecto_rollback_y_reintento(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    efecto, ejecuciones = _efecto_instrumentado(t)

    def explota(s):
        efecto(s)  # escribe el legajo… y después muere dentro de la misma transacción
        raise ErrorDeDominio("fallo de negocio")

    with pytest.raises(ErrorDeDominio):
        _run(t, "k-c2", explota)
    assert _legajos(t) == 0  # rollback completo del efecto
    assert _fila(t, "k-c2")["estado"] == "en_proceso"  # la reserva queda, recuperable
    assert _run(t, "k-c2", efecto)["ok"] and ejecuciones["n"] == 2 and _legajos(t) == 1


# ------------------------------------------------------------------ autorización / actor


def test_6_usuario_no_autorizado_no_obtiene_replay_ajeno(cliente_api, tenant_de_prueba):
    """A (responsable) ejecuta con clave K. B (supervisor, mismo tenant) reutiliza K en el
    mismo endpoint: no obtiene la respuesta de A — B pasa por autorización (403) y no
    queda ninguna fila a su nombre. Otro responsable C con K ejecuta su propio efecto."""
    t = tenant_de_prueba
    body = {"tipo_sujeto": "persona", "identificador_natural": "DNI-90"}
    ra = cliente_api.post("/v1/comandos/alta_de_sujeto", json=body, headers=t.headers("responsable_legajos", idempotency_key="K"))
    assert ra.status_code == 200
    rb = cliente_api.post("/v1/comandos/alta_de_sujeto", json=body, headers=t.headers("supervisor", idempotency_key="K"))
    assert rb.status_code == 403 and "sujeto_id" not in rb.text
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.idempotency_keys WHERE actor_id = :a"),
                         {"a": t.usuarios["supervisor"]}).scalar() == 0
    # y con un segundo responsable: ámbito propio → ejecuta de nuevo (409 de dominio porque
    # el identificador ya existe), nunca el replay de A
    from tests.conftest import token_para
    c = str(uuid.uuid4())
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles) "
                       "VALUES (:u, :t, :e, 'resp2', 'x', ARRAY['responsable_legajos'])"), {"u": c, "t": t.tenant_id, "e": f"r2@{t.slug}.t"})
    hc = {"Authorization": f"Bearer {token_para(t.tenant_id, c, ['responsable_legajos'])}", "Idempotency-Key": "K"}
    rc = cliente_api.post("/v1/comandos/alta_de_sujeto", json=body, headers=hc)
    assert rc.status_code == 409 and rc.json()["error"]["codigo"] == "conflicto"
    assert rc.json() != ra.json()


def test_http_dos_requests_simultaneos_no_ejecutan_dos_veces(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    body = {"tipo_sujeto": "persona", "identificador_natural": "DNI-77"}
    h = t.headers("responsable_legajos", idempotency_key="k-http")
    salidas = _en_paralelo([lambda: cliente_api.post("/v1/comandos/alta_de_sujeto", json=body, headers=h)] * 2)
    assert sorted(r.status_code for r, _ in salidas) == [200, 409]
    ok = next(r for r, _ in salidas if r.status_code == 200)
    assert cliente_api.post("/v1/comandos/alta_de_sujeto", json=body, headers=h).json() == ok.json()
    otro = cliente_api.post("/v1/comandos/alta_de_sujeto", json={**body, "identificador_natural": "DNI-78"}, headers=h)
    assert otro.status_code == 409 and otro.json()["error"]["codigo"] == "clave_idempotencia_reutilizada"
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.legajo")).scalar() == 1


# ------------------------------------------------------------------ lotes


def _lote_body(cliente_api, t, cuantas: int = 1):
    from tests.test_comandos_legajos import _alta_def, _alta_persona

    req = _alta_def(cliente_api, t, f"Apto-{uuid.uuid4().hex[:4]}")
    personas = [_alta_persona(cliente_api, t, f"L-{uuid.uuid4().hex[:6]}") for _ in range(cuantas)]
    filas = [{"sujeto_id": p, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"}
             for p in personas]
    return {"lote_id": str(uuid.uuid4()), "origen": "planilla", "filas": filas}, req, personas


def test_7_mismo_lote_id_con_filas_distintas_es_409_y_mismo_contenido_es_replay(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    body, req, personas = _lote_body(cliente_api, t, 2)
    h1, h2 = (t.headers("responsable_legajos", idempotency_key=k) for k in ("h1", "h2"))
    r1 = cliente_api.post("/v1/comandos/importar_lote", json=body, headers=h1)
    r2 = cliente_api.post("/v1/comandos/importar_lote", json=body, headers=h2)  # otro header, mismo lote y contenido
    assert r1.status_code == 200 and r2.status_code == 200 and r1.json() == r2.json()
    cambiado = {**body, "filas": body["filas"][:1]}  # mismo lote_id, filas distintas
    r3 = cliente_api.post("/v1/comandos/importar_lote", json=cambiado, headers=h1)
    assert r3.status_code == 409 and r3.json()["error"]["codigo"] == "clave_idempotencia_reutilizada"
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.lote_importacion")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM modulo1.documento")).scalar() == 2
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'LoteAplicado'")).scalar() == 1
    # entre actores distintos la red de seguridad es de dominio: mismo lote_id, otro contenido → 409
    from tests.conftest import token_para
    c = str(uuid.uuid4())
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles) "
                       "VALUES (:u, :t, :e, 'resp2', 'x', ARRAY['responsable_legajos'])"), {"u": c, "t": t.tenant_id, "e": f"r3@{t.slug}.t"})
    hc = {"Authorization": f"Bearer {token_para(t.tenant_id, c, ['responsable_legajos'])}"}
    r4 = cliente_api.post("/v1/comandos/importar_lote", json=cambiado, headers=hc)
    assert r4.status_code == 409 and r4.json()["error"]["codigo"] == "lote_contenido_distinto"
    # para C la clave `lote:<id>` quedó atada al fingerprint de su primer intento (regla
    # permanente): mismo contenido ahora es 409 de transporte, no un replay ajeno
    assert cliente_api.post("/v1/comandos/importar_lote", json=body, headers=hc).status_code == 409
    # un cuarto actor con el MISMO contenido: ya aplicado, sin reaplicar
    d = str(uuid.uuid4())
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.usuario (usuario_id, tenant_id, email, nombre, password_hash, roles) "
                       "VALUES (:u, :t, :e, 'resp3', 'x', ARRAY['responsable_legajos'])"), {"u": d, "t": t.tenant_id, "e": f"r4@{t.slug}.t"})
    hd = {"Authorization": f"Bearer {token_para(t.tenant_id, d, ['responsable_legajos'])}"}
    r5 = cliente_api.post("/v1/comandos/importar_lote", json=body, headers=hd)
    assert r5.status_code == 200 and r5.json()["ya_aplicado"] is True
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.documento")).scalar() == 2


# ------------------------------------------------------------------ autorización dinámica


def test_9_alcance_actual_se_valida_antes_del_replay(cliente_api, tenant_de_prueba, sesion):
    """Supervisor otorga una excepción sobre un sujeto de su universo (respuesta idempotente
    completada). Se cierra su asignación. Repite exactamente la misma clave y fingerprint:
    recibe 403/404 por alcance actual, no el replay almacenado, y no se repite el efecto."""
    from datetime import date, datetime, timezone

    from app.core.orquestacion import decidir_habilitacion
    from tests.test_orquestacion import clave_de_matriz, insertar_definicion, insertar_legajo, insertar_matriz, insertar_oc

    t = tenant_de_prueba
    clave = clave_de_matriz()
    insertar_legajo(sesion, t.tenant_id, "empresa_0001", "empresa")
    insertar_legajo(sesion, t.tenant_id, "persona_A", "persona")
    req = insertar_definicion(sesion, t.tenant_id, "Apto", "persona")
    insertar_matriz(sesion, t.tenant_id, clave, {req: "excepcionable"})
    insertar_oc(sesion, t.tenant_id, "OC-1", clave, date(2026, 10, 1), date(2026, 10, 5))
    sesion.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
                        "VALUES (:t, 'persona_A', :u, '2026-01-01', 'test')"), {"t": t.tenant_id, "u": t.usuarios["supervisor"]})
    ref = decidir_habilitacion(sesion, t.tenant_id, "OC-1", ["persona_A"], datetime(2026, 9, 18, tzinfo=timezone.utc),
                               t.usuarios["responsable_legajos"])["referencia_evaluacion"]
    sesion.commit()
    body = {"referencia_evaluacion": ref, "sujeto_id": "persona_A", "requisito_definicion_id": str(req),
            "commitment_id": "OC-1", "motivo": "regulariza"}
    h = t.headers("supervisor", idempotency_key="exc-1")
    r1 = cliente_api.post("/v1/comandos/otorgar_excepcion", json=body, headers=h)
    assert r1.status_code == 200, r1.text
    assert _fila(t.tenant_id, "exc-1", actor=t.usuarios["supervisor"])["estado"] == "completada"
    # el supervisor pierde el universo
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.asignacion_supervisor SET estado = 'cerrada', hasta = '2026-09-01' WHERE sujeto_id = 'persona_A'"))
    r2 = cliente_api.post("/v1/comandos/otorgar_excepcion", json=body, headers=h)  # misma clave, mismo fingerprint
    assert r2.status_code in (403, 404), r2.text
    assert "excepcion_id" not in r2.text
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.excepcion")).scalar() == 1  # efecto no repetido
    # recupera el universo → vuelve a obtener el replay (misma excepción, sin crear otra)
    with tenant_session(t.tenant_id) as s:
        s.execute(text("UPDATE modulo1.asignacion_supervisor SET estado = 'vigente', hasta = NULL WHERE sujeto_id = 'persona_A'"))
    r3 = cliente_api.post("/v1/comandos/otorgar_excepcion", json=body, headers=h)
    assert r3.status_code == 200 and r3.json() == r1.json()
