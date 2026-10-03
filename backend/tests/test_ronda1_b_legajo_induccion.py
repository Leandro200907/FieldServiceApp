"""GET /consultas/legajo con inducciones por locación y cobertura del sembrado demo."""
from __future__ import annotations

import os
import uuid

from sqlalchemy import text

from app.db import platform_session, tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post
from tests.test_sembrar_demo import TENANTS_DEMO, _exigir_base_demo_tests


def test_legajo_con_induccion_por_locacion_responde_200(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    loc = str(uuid.uuid4())
    req_doc = _alta_def(cliente_api, t, "Evidencia inducción legajo")
    req_ind = _alta_def(cliente_api, t, "Inducción legajo consulta", "induccion", locacion_id=loc)
    sujeto = _alta_persona(cliente_api, t, "40111222", nombre_apellido="Con Inducción")
    evidencia = _cargar(cliente_api, t, sujeto, req_doc)["documento_id"]
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
                "evidencia": evidencia,
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


def test_sembrado_demo_todos_los_legajos_consultables(demo_sembrado, cliente_api):
    """Cada legajo del sembrado demo debe poder abrirse sin error de serialización."""
    _exigir_base_demo_tests()
    password = os.environ.get("DEMO_PASSWORD", "demo-secreto-12")
    for slug in TENANTS_DEMO:
        login = cliente_api.post(
            "/v1/auth/login",
            json={
                "tenant_slug": slug,
                "email": f"responsable_legajos1@{slug}.demo.test",
                "password": password,
            },
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        with platform_session() as ps:
            tid = ps.execute(text("SELECT modulo1.resolver_tenant_por_slug(:s)"), {"s": slug}).scalar()
        assert tid is not None
        with tenant_session(str(tid)) as s:
            sujetos = [row[0] for row in s.execute(text("SELECT sujeto_id FROM modulo1.legajo ORDER BY sujeto_id")).all()]
        assert sujetos, f"{slug}: sin legajos en sembrado"
        for sujeto_id in sujetos:
            r = cliente_api.get(
                "/v1/consultas/legajo",
                params={"sujeto_id": sujeto_id},
                headers=headers,
            )
            assert r.status_code == 200, f"{slug}/{sujeto_id}: {r.status_code} {r.text}"
