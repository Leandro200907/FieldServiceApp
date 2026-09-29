"""B-1: drenaje_outbox con transporte disabled."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.comun.eventos import encolar_outbox
from app.db import tenant_session
from app.worker.cola import encolar
from app.worker.main import handler_drenaje_outbox, procesar_cola
from app.worker.outbox import PublicadorEnMemoria


def test_drenaje_outbox_job_no_publica_si_transporte_disabled(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    pub = PublicadorEnMemoria()
    with tenant_session(t) as s:
        encolar_outbox(s, t, "DocumentoVerificado", {"documento_id": str(uuid.uuid4())})
        jid = encolar(s, "drenaje_outbox", {}, tenant_id=t)
    ctx = {"publicador": pub, "drenar_outbox_habilitado": False}
    assert procesar_cola(t, "drenaje_outbox", handler_drenaje_outbox, ctx) == 1
    assert pub.eventos == []
    with tenant_session(t) as s:
        assert s.execute(text("SELECT procesado_en FROM modulo1.outbox_events")).scalar() is None
        assert s.execute(text("SELECT estado FROM modulo1.job_queue WHERE id = :id"), {"id": jid}).scalar() == "fallido"
