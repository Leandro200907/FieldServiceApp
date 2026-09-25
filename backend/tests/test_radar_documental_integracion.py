Warning: truncated output (original token count: 1912)
Total output lines: 116

"""Integración del radar contra PostgreSQL real y contrato HTTP."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.db import tenant_session


def _sembrar(t):
    ids = {k: str(uuid.uuid4()) for k in (
        "cliente", "locacion", "servicio", "oc", "oc_sin_matriz", "matriz_1", "matriz_2",
        "req_persona", "req_equipo", "custodia",
    )}
    with tenant_session(t.tenant_id) as s:
        for sujeto, tipo, nombre in (
            ("empresa-1", "empresa", "Empresa Uno"),
            ("persona-1", "persona", "Persona Uno"),
            ("vehiculo-1", "vehiculo", "AA000AA"),
            ("equipo-1", "equipo", "Equipo Uno"),
        ):
            s.execute(text("INSERT INTO modulo1.legajo (tenant_id,sujeto_id,tipo_sujeto,identificador_natural) VALUES (:t,:s,:ts,:n)"),
                      {"t": t.tenant_id, "s": sujeto, "ts": tipo, "n": nombre})
        for rid, nombre, categoria, tipo in (
            (ids["req_persona"], "Apto médico", "documento", "persona"),
            (ids["req_equipo"], "Calibración especial", "documento", "equipo"),
        ):
            s.execute(text("INSERT INTO modulo1.definicion_requisito (requisito_definicion_id,tenant_id,nombre,categoria,tipo_sujeto_aplicable) VALUES (:r,:t,:n,:c,:ts)"),
                      {"r": rid, "t": t.tenant_id, "n": nombre, "c": categoria, "ts": tipo})
        for mid, version, desde, hasta in (
            (ids["matriz_1"], 1, date(2026, 1, 1), date(2026, 10, 15)),
            (ids["matriz_2"], 2, date(2026, 10, 16), None),
        ):
            s.execute(text("INSERT INTO modulo1.matriz_requisitos (matriz_version_id,tenant_id,cliente_id,locacion_id,tipo_servicio_id,version,vigente_desde,vigente_hasta,fuente) VALUES (:m,:t,:c,:l,:ts,:v,:d,:h,'prueba')"),
                      {"m": mid, "t": t.tenant_id, "c": ids["cliente"], "l": ids["locacion"], "ts": ids["servicio"], "v": version, "d": desde, "h": hasta})
            s.execute(tex…912 tokens truncated…
                  {"t": tenant_de_prueba.tenant_id, "c": ids["custodia"]})
    despues = cliente_api.get(_url(), headers=headers).json()["items"]
    assert despues == antes


def test_cambio_documental_modifica_el_resultado_del_legajo(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba); headers = tenant_de_prueba.headers("supervisor")
    url = f"/v1/consultas/radar_documental_oc/{ids['oc']}/legajos/persona-1"
    assert cliente_api.get(url, headers=headers).json()["legajo"]["estado_documental"] == "con_alertas_documentales"
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.documento (tenant_id,sujeto_id,requisito_definicion_id,vigente_desde,vigente_hasta,estado_confirmacion,origen) VALUES (:t,'persona-1',:r,'2026-01-01','2026-12-31','verificado','carga_manual')"),
                  {"t": tenant_de_prueba.tenant_id, "r": ids["req_persona"]})
    assert cliente_api.get(url, headers=headers).json()["legajo"]["estado_documental"] == "sin_alertas_documentales"


def test_permisos_y_openapi(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    assert cliente_api.get(_url(), headers=tenant_de_prueba.headers("configuracion")).status_code == 200
    assert cliente_api.get(_url(), headers=tenant_de_prueba.headers("tecnico")).status_code == 403
    detalle = f"/v1/consultas/radar_documental_oc?oc_id={ids['oc']}"
    assert cliente_api.get(detalle, headers=tenant_de_prueba.headers("configuracion")).status_code == 403
    esquema = cliente_api.get("/openapi.json").json()
    for ruta in (
        "/v1/consultas/radar_documental_backlog",
        "/v1/consultas/radar_documental_oc",
        "/v1/consultas/radar_documental_oc/{oc_id}/legajos/{sujeto_id}",
    ):
        assert ruta in esquema["paths"]
    contrato = str(esquema["paths"]["/v1/consultas/radar_documental_backlog"])
    assert not any(p in contrato for p in ("asignable", "candidato", "capacidad_documental", "bajo_excepcion"))

