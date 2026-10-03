"""Historial append-only de estados ante operadora (0029)."""
from __future__ import annotations

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar
from tests.test_operadoras_documentales import _registrar


def test_misma_version_deja_un_movimiento_por_cada_paso(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Seguro vehicular")
    sujeto = _alta_persona(cliente_api, t, "movimientos espejo")
    doc = _cargar(cliente_api, t, sujeto, req, desde="2026-02-01", hasta="2027-02-01")

    secuencia = [
        ("enviado", {"exportado_en": "2026-02-02T08:00:00Z", "enviado_en": "2026-02-02T09:00:00Z"}),
        ("rechazado", {"rechazado_en": "2026-02-03T10:00:00Z", "observacion": "Falta firma"}),
        ("enviado", {"enviado_en": "2026-02-04T11:00:00Z"}),
        ("aceptado", {"aceptado_en": "2026-02-05T12:00:00Z"}),
    ]
    for estado, extras in secuencia:
        _registrar(
            cliente_api,
            t,
            sujeto_id=sujeto,
            documento_id=doc["documento_id"],
            estado=estado,
            **extras,
        )

    with tenant_session(t.tenant_id) as session:
        filas = session.execute(
            text("""
                SELECT estado FROM modulo1.movimiento_entrega_operadora
                WHERE documento_id = :d ORDER BY paso_en ASC, creado_en ASC
            """),
            {"d": doc["documento_id"]},
        ).scalars().all()
    assert filas == ["enviado", "rechazado", "enviado", "aceptado"]
