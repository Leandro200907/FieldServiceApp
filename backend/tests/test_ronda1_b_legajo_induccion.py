"""GET /consultas/legajo con inducciones por locación."""
from __future__ import annotations

import uuid

from tests.apoyo_e97 import certificado_subido
from tests.test_comandos_legajos import _alta_def, _alta_persona, _ok, _post


def test_legajo_con_induccion_por_locacion_responde_200(cliente_api, tenant_de_prueba, storage):
    t = tenant_de_prueba
    loc = str(uuid.uuid4())
    req_ind = _alta_def(cliente_api, t, "Inducción legajo consulta", "induccion", locacion_id=loc)
    sujeto = _alta_persona(cliente_api, t, "40111222", nombre_apellido="Con Inducción")
    cert = certificado_subido(cliente_api, storage, t, sujeto)
    _ok(
        _post(
            cliente_api,
            t,
            "responsable_legajos",
            "registrar_induccion",
            {
                "persona_id": sujeto,
                "locacion_id": loc,
                "requisito_definicion_id": req_ind,
                "certificado_documento_id": cert,
                "vigente_desde": "2026-03-01",
                "vigente_hasta": "2027-03-01",
            },
        )
    )
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": sujeto}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    inducciones = r.json()["inducciones"]
    assert len(inducciones) == 1
    assert inducciones[0]["locacion_id"] == loc
    assert isinstance(inducciones[0]["locacion_id"], str)
