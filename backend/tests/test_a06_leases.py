"""A-06 de la auditoría: leases de job_queue con propietario (`lease_token`).

Todas las operaciones sobre un job en curso exigen el token de quien lo tomó y se
verifican con `UPDATE … WHERE lease_token = … RETURNING` (exactamente una fila).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db import tenant_session
from app.worker.cola import LeaseAjeno, completar, encolar, fallar, renovar_lease, tomar


def _job(tenant_id: str, cola: str = "notificaciones") -> int:
    with tenant_session(tenant_id) as s:
        return encolar(s, cola, {"x": 1}, tenant_id)


def _fila(tenant_id: str, jid: int) -> dict:
    with tenant_session(tenant_id) as s:
        return dict(s.execute(text("SELECT estado, lease_token, lease_hasta, intentos FROM modulo1.job_queue WHERE id = :id"),
                              {"id": jid}).mappings().one())


def _vencer_lease(tenant_id: str, jid: int) -> None:
    with tenant_session(tenant_id) as s:
        s.execute(text("UPDATE modulo1.job_queue SET lease_hasta = now() - interval '1 second' WHERE id = :id"), {"id": jid})


def test_lease_token_nuevo_en_cada_adquisicion(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    jid = _job(t)
    with tenant_session(t) as s:
        j1 = tomar(s, "notificaciones", lease_seg=30)
    assert j1.id == jid and j1.lease_token is not None
    assert _fila(t, jid)["lease_token"] == j1.lease_token
    _vencer_lease(t, jid)
    with tenant_session(t) as s:
        j2 = tomar(s, "notificaciones", lease_seg=30)
    assert j2.id == jid and j2.lease_token != j1.lease_token
    # fuera de en_curso el token se limpia (CHECK en la base)
    with tenant_session(t) as s:
        completar(s, jid, j2.lease_token)
    assert _fila(t, jid) == {**_fila(t, jid), "estado": "completado", "lease_token": None, "lease_hasta": None}


def test_completar_y_fallar_exigen_token_propietario(tenant_de_prueba):
    import uuid

    t = tenant_de_prueba.tenant_id
    jid = _job(t)
    with tenant_session(t) as s:
        j = tomar(s, "notificaciones", lease_seg=30)
    with pytest.raises(LeaseAjeno):
        with tenant_session(t) as s:
            completar(s, jid, uuid.uuid4())  # token incorrecto
    with pytest.raises(LeaseAjeno):
        with tenant_session(t) as s:
            fallar(s, jid, uuid.uuid4())
    assert _fila(t, jid)["estado"] == "en_curso"
    with tenant_session(t) as s:
        completar(s, jid, j.lease_token)
    assert _fila(t, jid)["estado"] == "completado"
    # sobre un job ya completado, ni siquiera el token propietario puede volver a actuar
    with pytest.raises(LeaseAjeno):
        with tenant_session(t) as s:
            completar(s, jid, j.lease_token)


def test_trabajador_anterior_rechazado_tras_readquisicion(tenant_de_prueba):
    """Worker A toma el job, su lease vence, worker B lo readquiere. A intenta completar
    (y fallar) con su token viejo: rechazado, sin afectar la fila; B sí completa."""
    t = tenant_de_prueba.tenant_id
    jid = _job(t)
    with tenant_session(t) as s:
        ja = tomar(s, "notificaciones", lease_seg=30)
    _vencer_lease(t, jid)
    with tenant_session(t) as s:
        jb = tomar(s, "notificaciones", lease_seg=30)
    assert jb.id == jid and jb.lease_token != ja.lease_token
    for accion in (lambda s: completar(s, jid, ja.lease_token), lambda s: fallar(s, jid, ja.lease_token)):
        with pytest.raises(LeaseAjeno):
            with tenant_session(t) as s:
                accion(s)
    f = _fila(t, jid)
    assert f["estado"] == "en_curso" and f["lease_token"] == jb.lease_token
    with tenant_session(t) as s:
        completar(s, jid, jb.lease_token)
    assert _fila(t, jid)["estado"] == "completado"


def test_dos_workers_nunca_completan_la_misma_tarea(tenant_de_prueba):
    """Con lease vivo, el segundo worker no obtiene el job; con lease vencido lo readquiere
    y el primero pierde la propiedad. En ningún caso ambos completan."""
    t = tenant_de_prueba.tenant_id
    jid = _job(t)
    with tenant_session(t) as s:
        ja = tomar(s, "notificaciones", lease_seg=30)
    with tenant_session(t) as s:
        assert tomar(s, "notificaciones", lease_seg=30) is None  # lease vivo
    _vencer_lease(t, jid)
    with tenant_session(t) as s:
        jb = tomar(s, "notificaciones", lease_seg=30)
    completos = 0
    for token in (ja.lease_token, jb.lease_token):
        try:
            with tenant_session(t) as s:
                completar(s, jid, token)
            completos += 1
        except LeaseAjeno:
            pass
    assert completos == 1 and _fila(t, jid)["estado"] == "completado"


def test_renovar_lease_solo_por_su_propietario(tenant_de_prueba):
    import uuid

    t = tenant_de_prueba.tenant_id
    jid = _job(t)
    with tenant_session(t) as s:
        j = tomar(s, "notificaciones", lease_seg=5)
    antes = _fila(t, jid)["lease_hasta"]
    with pytest.raises(LeaseAjeno):
        with tenant_session(t) as s:
            renovar_lease(s, jid, uuid.uuid4(), lease_seg=600)
    assert _fila(t, jid)["lease_hasta"] == antes
    with tenant_session(t) as s:
        renovar_lease(s, jid, j.lease_token, lease_seg=600)
    assert _fila(t, jid)["lease_hasta"] > antes
    # un lease vencido no se renueva: hay que readquirir
    _vencer_lease(t, jid)
    with pytest.raises(LeaseAjeno):
        with tenant_session(t) as s:
            renovar_lease(s, jid, j.lease_token, lease_seg=600)


def test_efectos_del_worker_viejo_se_revierten_al_perder_el_lease(tenant_de_prueba):
    """Fencing real: el worker A corre un handler lento que ESCRIBE en la base; durante la
    ejecución su lease vence y el worker B readquiere y completa. Al terminar, A intenta
    confirmar: como completar() corre en la misma transacción que el handler y el lease
    ya no es suyo, todo lo que A escribió se revierte. Solo quedan los efectos de B."""
    from app.worker import main as worker_main

    t = tenant_de_prueba.tenant_id
    jid = _job(t, "notificaciones")

    def handler_a(s, job, ctx):
        # A escribe su efecto (evento) dentro de su transacción…
        s.execute(text("INSERT INTO modulo1.event_log (tenant_id, tipo, payload) VALUES (:t, 'EfectoDe', '{\"worker\": \"A\"}')"),
                  {"t": t})
        # …mientras tanto su lease vence y B readquiere, hace SU efecto y completa.
        _vencer_lease(t, job.id)
        with tenant_session(t) as sb:
            jb = tomar(sb, "notificaciones", lease_seg=30)
            assert jb is not None and jb.lease_token != job.lease_token
            sb.execute(text("INSERT INTO modulo1.event_log (tenant_id, tipo, payload) VALUES (:t, 'EfectoDe', '{\"worker\": \"B\"}')"),
                       {"t": t})
            completar(sb, job.id, jb.lease_token)
        # A sigue y "termina": procesar_cola llamará completar() con el token viejo en esta tx.

    n = worker_main.procesar_cola(t, "notificaciones", handler_a, {}, max_jobs=1)
    assert n == 1
    with tenant_session(t) as s:
        efectos = [p["worker"] for (p,) in s.execute(text("SELECT payload FROM modulo1.event_log WHERE tipo = 'EfectoDe'")).all()]
        assert efectos == ["B"]  # el efecto de A fue revertido junto con su intento de completar
        assert _fila(t, jid)["estado"] == "completado"
        assert s.execute(text("SELECT count(*) FROM modulo1.job_queue WHERE estado = 'completado'")).scalar() == 1


def test_procesar_cola_worker_lento_no_completa_tras_readquisicion(tenant_de_prueba):
    """Integración con el loop del worker: un handler que tarda más que el lease y un
    segundo worker que readquiere: solo uno completa, sin errores no controlados."""
    from app.worker import main as worker_main

    t = tenant_de_prueba.tenant_id
    jid = _job(t, "evidencia_qr")
    completados = []

    def handler_lento(s, job, ctx):
        _vencer_lease(t, job.id)  # simula que el lease expiró durante el trabajo
        with tenant_session(t) as s2:
            jb = tomar(s2, "evidencia_qr", lease_seg=30)  # otro worker readquiere
        assert jb is not None and jb.lease_token != job.lease_token
        with tenant_session(t) as s3:
            completar(s3, job.id, jb.lease_token)  # el otro worker termina
        completados.append("worker_b")

    n = worker_main.procesar_cola(t, "evidencia_qr", handler_lento, {}, max_jobs=1)
    assert n == 1 and completados == ["worker_b"]
    assert _fila(t, jid)["estado"] == "completado"
    with tenant_session(t) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.job_queue WHERE estado = 'completado'")).scalar() == 1
