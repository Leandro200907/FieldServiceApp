"""Worker apto para producción: nada se completa en silencio, backoff exponencial, máximo
de intentos, dead-letter terminal con último error saneado, mensajes venenosos sin loop,
dos workers con reloj controlado."""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db import tenant_session
from app.worker import cola as cola_mod
from app.worker import main as worker_main
from app.worker.cola import backoff_seg, encolar, fallar, sanear_error, tomar
from app.worker.outbox import PublicadorEnMemoria

T0 = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _job(t, cola="score_documental", payload=None):
    with tenant_session(t) as s:
        return encolar(s, cola, payload or {"x": 1}, tenant_id=t, disponible_en=T0)


def _fila(t, jid):
    with tenant_session(t) as s:
        return dict(s.execute(text("SELECT estado, intentos, disponible_en, ultimo_error, ultimo_error_en, fallido_en, lease_token "
                                   "FROM modulo1.job_queue WHERE id = :i"), {"i": jid}).mappings().one())


# --------------------------------------------------------------------------- backoff y máximo de intentos


def test_backoff_exponencial_con_tope():
    assert [backoff_seg(n) for n in (1, 2, 3, 4, 5, 6, 7, 8)] == [30, 60, 120, 240, 480, 960, 1920, 3600]
    assert backoff_seg(50) == 3600


def test_reintentos_con_reloj_controlado_hasta_dead_letter(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    jid = _job(t)
    ahora = T0
    for intento in range(1, 6):
        with tenant_session(t) as s:
            j = tomar(s, "score_documental", lease_seg=60, ahora=ahora)
            assert j is not None and j.intentos == intento
            estado = fallar(s, jid, j.lease_token, error=RuntimeError(f"fallo {intento}"), ahora=ahora)
        fila = _fila(t, jid)
        if intento < 5:
            assert estado == "pendiente"
            espera = backoff_seg(intento)
            assert fila["disponible_en"] == ahora + timedelta(seconds=espera)
            assert fila["ultimo_error"] == f"RuntimeError: fallo {intento}" and fila["fallido_en"] is None
            with tenant_session(t) as s:  # antes del backoff no se toma; justo al vencer, sí
                assert tomar(s, "score_documental", ahora=ahora + timedelta(seconds=espera - 1)) is None
            ahora = ahora + timedelta(seconds=espera)
        else:
            assert estado == "fallido"
    fila = _fila(t, jid)
    assert fila["estado"] == "fallido" and fila["intentos"] == 5 and fila["fallido_en"] == ahora
    assert fila["ultimo_error"] == "RuntimeError: fallo 5" and fila["lease_token"] is None
    # Terminal: ni con el reloj un año adelante se vuelve a tomar.
    with tenant_session(t) as s:
        assert tomar(s, "score_documental", ahora=ahora + timedelta(days=365)) is None


def test_lease_vencido_con_reloj_controlado_lo_retoma_otro_worker(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    jid = _job(t, "notificaciones")
    with tenant_session(t) as s:
        ja = tomar(s, "notificaciones", lease_seg=60, ahora=T0)
    with tenant_session(t) as s:
        assert tomar(s, "notificaciones", lease_seg=60, ahora=T0 + timedelta(seconds=59)) is None
        jb = tomar(s, "notificaciones", lease_seg=60, ahora=T0 + timedelta(seconds=61))
    assert jb is not None and jb.id == jid and jb.lease_token != ja.lease_token and jb.intentos == 2
    with tenant_session(t) as s, pytest.raises(cola_mod.LeaseAjeno):
        cola_mod.renovar_lease(s, jid, ja.lease_token, 60, ahora=T0 + timedelta(seconds=62))


# --------------------------------------------------------------------------- terminal / venenoso / stubs


def test_fallo_terminal_va_al_dead_letter_en_el_primer_intento(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    jid = _job(t)
    with tenant_session(t) as s:
        j = tomar(s, "score_documental", ahora=T0)
        assert fallar(s, jid, j.lease_token, error="payload inválido", terminal=True, ahora=T0) == "fallido"
    fila = _fila(t, jid)
    assert fila["estado"] == "fallido" and fila["intentos"] == 1 and fila["ultimo_error"] == "payload inválido" and fila["fallido_en"] == T0


@pytest.mark.parametrize("cola", ["evidencia_qr"])
def test_cola_sin_handler_no_se_completa_en_silencio(tenant_de_prueba, cola, caplog):
    t = tenant_de_prueba.tenant_id
    jid = _job(t, cola)
    handlers = worker_main.handlers_completos()
    assert set(handlers) == set(cola_mod.COLAS)
    with caplog.at_level(logging.ERROR, logger="modulo1.worker"):
        n = worker_main.procesar_cola(t, cola, handlers[cola], {}, ahora=T0)
    fila = _fila(t, jid)
    assert n == 1 and fila["estado"] == "fallido" and fila["intentos"] == 1
    assert fila["ultimo_error"] == f"JobNoProcesable: cola {cola}: handler no implementado en esta versión"
    assert "dead-letter" in caplog.text and str(jid) in caplog.text


def test_mensaje_venenoso_no_se_reintenta_en_loop(tenant_de_prueba):
    """Un handler que revienta siempre: exactamente MAX_INTENTOS ejecuciones y después
    dead-letter; las vueltas siguientes no lo tocan más."""
    t = tenant_de_prueba.tenant_id
    jid = _job(t, "notificaciones", {"tipo": "X"})
    ejecuciones = []

    def veneno(session, job, contexto):
        ejecuciones.append(job.intentos)
        raise ValueError("siempre falla")

    ahora = T0
    for _ in range(20):  # muchas vueltas; sólo 5 llegan al handler
        worker_main.procesar_cola(t, "notificaciones", veneno, {}, ahora=ahora)
        ahora += timedelta(hours=2)  # más que cualquier backoff
    assert ejecuciones == [1, 2, 3, 4, 5]
    fila = _fila(t, jid)
    assert fila["estado"] == "fallido" and fila["ultimo_error"] == "ValueError: siempre falla"


def test_notificacion_sin_tipo_es_terminal_y_con_tipo_sale_por_el_canal(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    enviadas = []

    class Canal:
        def enviar(self, tenant_id, notificacion):
            enviadas.append((tenant_id, notificacion))

    j_mal = _job(t, "notificaciones", {"sin": "tipo"})
    j_ok = _job(t, "notificaciones", {"tipo": "AlertaDeVencimientoAbierta", "sujeto": "p"})
    worker_main.procesar_cola(t, "notificaciones", worker_main.handler_notificaciones, {"canal_notificaciones": Canal()}, ahora=T0)
    assert _fila(t, j_mal)["estado"] == "fallido" and "sin `tipo`" in _fila(t, j_mal)["ultimo_error"]
    assert _fila(t, j_ok)["estado"] == "completado" and enviadas == [(t, {"tipo": "AlertaDeVencimientoAbierta", "sujeto": "p"})]


# --------------------------------------------------------------------------- último error saneado


@pytest.mark.parametrize("crudo, esperado", [
    ("Authorization: Bearer eyJhbGciOi.abc.def falló", "Authorization: Bearer [redactado] falló"),
    ("conexión postgresql://modulo1_app:clave-de-prueba-1@localhost:5432/x rechazada", "conexión postgresql://modulo1_app:[redactado]@localhost:5432/x rechazada"),
    ("password=hunter2 token: abc api_key=xyz", "password=[redactado] token: [redactado] api_key=[redactado]"),
    ("x" * 900, "x" * 500),
])
def test_sanear_error_redacta_y_trunca(crudo, esperado):
    assert sanear_error(crudo) == esperado
    assert sanear_error(RuntimeError(crudo)) == ("RuntimeError: " + esperado)[:500]
    assert sanear_error(None) is None


def test_el_dead_letter_no_guarda_secretos(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    jid = _job(t, "notificaciones", {"tipo": "X"})

    def handler(session, job, contexto):
        raise ConnectionError("no pude llamar con Bearer secreto.token.123 a postgresql://u:clave@h/db")

    worker_main.procesar_cola(t, "notificaciones", handler, {}, ahora=T0, max_intentos=1)
    err = _fila(t, jid)["ultimo_error"]
    assert "secreto.token.123" not in err and "clave@" not in err and "[redactado]" in err


# --------------------------------------------------------------------------- dos workers


def test_dos_workers_con_reloj_controlado_reparten_sin_duplicar(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    ids = [_job(t, "notificaciones", {"tipo": "X", "n": i}) for i in range(8)]
    vistos: dict[int, list[str]] = {}
    lock = threading.Lock()
    barrera = threading.Barrier(2)

    def handler_de(nombre):
        def handler(session, job, contexto):
            with lock:
                vistos.setdefault(job.id, []).append(nombre)
        return handler

    def worker(nombre):
        barrera.wait()
        worker_main.procesar_cola(t, "notificaciones", handler_de(nombre), {}, ahora=T0)

    hilos = [threading.Thread(target=worker, args=(n,)) for n in ("A", "B")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(30)
    assert sorted(vistos) == sorted(ids)
    assert all(len(v) == 1 for v in vistos.values())            # ningún job procesado dos veces
    with tenant_session(t) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.job_queue WHERE tenant_id = :t AND estado = 'completado'"), {"t": t}).scalar() == 8


def test_dos_workers_reintentos_y_dead_letter_con_reloj(tenant_de_prueba):
    """Dos workers alternando sobre un job que falla: cada intento respeta el backoff del
    reloj controlado, nadie lo toma antes de tiempo y termina en dead-letter con 5 intentos."""
    t = tenant_de_prueba.tenant_id
    jid = _job(t, "notificaciones", {"tipo": "X"})
    ejecuciones = []

    def falla(session, job, contexto):
        ejecuciones.append(job.intentos)
        raise RuntimeError("no")

    ahora = T0
    for vuelta in range(5):
        # los dos workers en la misma vuelta: sólo uno toma el job, el otro no ve nada
        n_a = worker_main.procesar_cola(t, "notificaciones", falla, {}, ahora=ahora)
        n_b = worker_main.procesar_cola(t, "notificaciones", falla, {}, ahora=ahora)
        assert (n_a, n_b) == (1, 0)
        fila = _fila(t, jid)
        if vuelta < 4:
            assert fila["estado"] == "pendiente" and fila["disponible_en"] == ahora + timedelta(seconds=backoff_seg(vuelta + 1))
            ahora = fila["disponible_en"]
    assert ejecuciones == [1, 2, 3, 4, 5] and _fila(t, jid)["estado"] == "fallido"


def test_correr_una_vuelta_acepta_reloj_y_canal(tenant_de_prueba):
    class _Storage:
        def clave_para(self, *a): return "x"
        def existe(self, c): return False
        def inspeccionar(self, c): return None
        def borrar(self, c): return True
        def disponible(self): return True
    t = tenant_de_prueba.tenant_id
    _job(t, "validacion_evidencia")
    resumen = worker_main.correr_una_vuelta(_Storage(), PublicadorEnMemoria(), ahora=T0)
    assert resumen["jobs"] >= 1
    with tenant_session(t) as s:
        fila = s.execute(text("SELECT estado, fallido_en FROM modulo1.job_queue WHERE tenant_id = :t AND cola = 'validacion_evidencia'"), {"t": t}).one()
    assert fila[0] == "fallido" and fila[1] == T0
