"""E-109: importar_lote no admite filas verificadas; solo declarado (D20) y confirmación normal."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _confirmar_con_respaldo, _docs, _ok, _post


def test_e109_importar_lote_rechaza_fila_verificada(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "E109 rechazo")
    persona = _alta_persona(cliente_api, t, "DNI-E109-R")
    r = _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "importar_lote",
            {
                "lote_id": str(uuid.uuid4()),
                "filas": [
                    {
                        "sujeto_id": persona,
                        "requisito_definicion_id": req,
                        "vigente_desde": "2026-01-01",
                        "vigente_hasta": "2026-12-31",
                        "estado_confirmacion": "verificado",
                    }
                ],
            },
        )
    )
    assert r["filas_aceptadas"] == 0 and r["filas_rechazadas"] == 1
    assert r["detalle_filas_rechazadas"][0]["codigo"] == "lote_no_admite_verificado"
    with tenant_session(t.tenant_id) as s:
        n = s.execute(
            text(
                "SELECT count(*) FROM modulo1.documento WHERE sujeto_id = :s AND requisito_definicion_id = CAST(:r AS uuid)"
            ),
            {"s": persona, "r": req},
        ).scalar()
    assert n == 0


def test_e109_importar_lote_declarado_y_confirmacion_normal(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "E109 ok")
    persona = _alta_persona(cliente_api, t, "DNI-E109-O")
    lote = str(uuid.uuid4())
    r = _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "importar_lote",
            {
                "lote_id": lote,
                "filas": [
                    {
                        "sujeto_id": persona,
                        "requisito_definicion_id": req,
                        "vigente_desde": "2026-01-01",
                        "vigente_hasta": "2026-12-31",
                    }
                ],
            },
        )
    )
    assert r["filas_aceptadas"] == 1
    assert _docs(t, persona, req)[0]["estado_confirmacion"] == "declarado"
    doc_id = _docs(t, persona, req)[0]["documento_id"]
    conf = _confirmar_con_respaldo(cliente_api, t, doc_id)
    assert "DocumentoVerificado" in conf.get("eventos", [])
    assert _docs(t, persona, req)[0]["estado_confirmacion"] == "verificado"
