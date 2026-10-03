"""B-8: prefijos distintos de idempotencia para lotes de legajos y OC."""
from __future__ import annotations

import uuid

from tests.test_comandos_legajos import _alta_def, _alta_persona, _post, _ok


def _fila_oc(clave: str) -> dict:
    return {
        "clave_origen": clave,
        "cliente_id": str(uuid.uuid4()),
        "locacion_id": str(uuid.uuid4()),
        "tipo_servicio_id": str(uuid.uuid4()),
        "vigencia_desde": "2026-01-01",
        "vigencia_hasta": "2026-12-31",
    }


def test_mismo_lote_id_en_legajos_y_oc_no_colisiona(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    lote_id = str(uuid.uuid4())
    req = _alta_def(cliente_api, t, "Lote prefijo")
    p = _alta_persona(cliente_api, t, "lote-pref")
    r_doc = _ok(_post(cliente_api, t, "responsable_legajos", "importar_lote", {
        "lote_id": lote_id, "origen": "planilla",
        "filas": [{"sujeto_id": p, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"}],
    }))
    r_oc = cliente_api.post("/v1/comandos/importar_lote_oc", json={
        "lote_id": lote_id, "origen": "planilla", "filas": [_fila_oc("OC-PREF")],
    }, headers=t.headers("responsable_legajos"))
    assert r_oc.status_code == 200, r_oc.text
    assert r_doc["lote_id"] == lote_id and r_oc.json()["lote_id"] == lote_id
