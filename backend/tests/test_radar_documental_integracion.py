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
            s.execute(text("INSERT INTO modulo1.linea_requisito (matriz_version_id,requisito_definicion_id,tenant_id,clasificacion,bloqueante_durante_ejecucion) VALUES (:m,:r,:t,'bloqueante_duro',true)"),
                      {"m": mid, "r": ids["req_persona"], "t": t.tenant_id})
        s.execute(text("INSERT INTO modulo1.oc (oc_id,tenant_id,clave_origen,referencia,cliente_id,locacion_id,tipo_servicio_id,vigencia_desde,vigencia_hasta) VALUES (:id,:t,'OC-RADAR','Radar',:c,:l,:ts,'2026-10-10','2026-10-20')"),
                  {"id": ids["oc"], "t": t.tenant_id, "c": ids["cliente"], "l": ids["locacion"], "ts": ids["servicio"]})
        s.execute(text("INSERT INTO modulo1.oc (oc_id,tenant_id,clave_origen,referencia,cliente_id,locacion_id,tipo_servicio_id,vigencia_desde,vigencia_hasta) VALUES (:id,:t,'OC-SIN-MATRIZ','Sin matriz',gen_random_uuid(),:l,:ts,'2026-10-10','2026-10-20')"),
                  {"id": ids["oc_sin_matriz"], "t": t.tenant_id, "l": ids["locacion"], "ts": ids["servicio"]})
        s.execute(text("INSERT INTO modulo1.requisito_particular (tenant_id,commitment_id,requisito_definicion_id,clasificacion,bloqueante_durante_ejecucion) VALUES (:t,'OC-RADAR',:r,'bloqueante_duro',true)"),
                  {"t": t.tenant_id, "r": ids["req_equipo"]})
    return ids


def _url():
    return "/v1/consultas/radar_documental_backlog?desde=2026-10-01&hasta=2026-11-30"


def test_todos_los_legajos_aparecen_sin_asignacion_ni_custodia(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    respuesta = cliente_api.get(_url(), headers=tenant_de_prueba.headers("supervisor"))
    assert respuesta.status_code == 200, respuesta.text
    items = {i["oc_id"]: i for i in respuesta.json()["items"]}
    radar = items[ids["oc"]]
    assert {k: radar["resumen"][k]["total"] for k in ("empresa", "personas", "vehiculos", "equipos")} == {
        "empresa": 1, "personas": 1, "vehiculos": 1, "equipos": 1,
    }
    assert items[ids["oc_sin_matriz"]]["estado_documental"] == "sin_matriz"


def test_detalle_usa_dos_versiones_y_requisito_particular(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    respuesta = cliente_api.get(f"/v1/consultas/radar_documental_oc?oc_id={ids['oc']}", headers=tenant_de_prueba.headers("supervisor"))
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [m["version"] for m in cuerpo["matrices_utilizadas"]] == [1, 2]
    assert [r["nombre"] for r in cuerpo["requisitos_particulares"]] == ["Calibración especial"]
    equipo = next(g for g in cuerpo["grupos"] if g["tipo_sujeto"] == "equipo")["legajos"][0]
    assert {r["nombre"] for r in equipo["requisitos"]} == {"Calibración especial"}


def test_tipo_requerido_sin_legajos_no_produce_falso_verde(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.documento "
                       "(tenant_id,sujeto_id,requisito_definicion_id,vigente_desde,vigente_hasta,estado_confirmacion,origen) "
                       "VALUES (:t,'equipo-1',:r,'2026-01-01','2026-12-31','verificado','carga_manual')"),
                  {"t": tenant_de_prueba.tenant_id, "r": ids["req_equipo"]})
        s.execute(text("DELETE FROM modulo1.legajo WHERE tenant_id=:t AND tipo_sujeto='persona'"),
                  {"t": tenant_de_prueba.tenant_id})
    respuesta = cliente_api.get(_url(), headers=tenant_de_prueba.headers("supervisor"))
    item = next(i for i in respuesta.json()["items"] if i["oc_id"] == ids["oc"])
    assert item["estado_documental"] == "informacion_incompleta"
    assert any("tipo persona" in motivo for motivo in item["motivos_resumidos"])


def test_hueco_parcial_de_matriz_no_oculta_alertas_reales(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        s.execute(text("UPDATE modulo1.matriz_requisitos SET vigente_hasta='2026-10-14' "
                       "WHERE tenant_id=:t AND matriz_version_id=CAST(:m AS uuid)"),
                  {"t": tenant_de_prueba.tenant_id, "m": ids["matriz_1"]})
    respuesta = cliente_api.get(_url(), headers=tenant_de_prueba.headers("supervisor"))
    item = next(i for i in respuesta.json()["items"] if i["oc_id"] == ids["oc"])
    assert item["estado_documental"] == "con_alertas_documentales"
    assert "Hay períodos sin matriz de requisitos aplicable" in item["motivos_resumidos"]


def test_requisito_particular_se_evalua_aun_sin_matriz(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.requisito_particular "
                       "(tenant_id,commitment_id,requisito_definicion_id,clasificacion,bloqueante_durante_ejecucion) "
                       "VALUES (:t,'OC-SIN-MATRIZ',:r,'bloqueante_duro',true)"),
                  {"t": tenant_de_prueba.tenant_id, "r": ids["req_equipo"]})
    respuesta = cliente_api.get(
        f"/v1/consultas/radar_documental_oc?oc_id={ids['oc_sin_matriz']}",
        headers=tenant_de_prueba.headers("supervisor"),
    )
    cuerpo = respuesta.json()
    equipo = next(g for g in cuerpo["grupos"] if g["tipo_sujeto"] == "equipo")["legajos"][0]
    assert cuerpo["estado_documental"] == "con_alertas_documentales"
    assert {r["nombre"] for r in equipo["requisitos"]} == {"Calibración especial"}
    assert cuerpo["huecos_matriz"] == [{"desde": "2026-10-10", "hasta": "2026-10-20"}]


def test_backlog_y_detalle_respetan_paginacion(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    headers = tenant_de_prueba.headers("supervisor")
    backlog = cliente_api.get(_url() + "&limit=1", headers=headers).json()
    assert backlog["total"] == 2
    assert len(backlog["items"]) == 1
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.legajo "
                       "(tenant_id,sujeto_id,tipo_sujeto,identificador_natural) "
                       "VALUES (:t,'persona-2','persona','Persona Dos')"),
                  {"t": tenant_de_prueba.tenant_id})
    detalle = cliente_api.get(
        f"/v1/consultas/radar_documental_oc?oc_id={ids['oc']}&limit=1", headers=headers,
    ).json()
    personas = next(g for g in detalle["grupos"] if g["tipo_sujeto"] == "persona")
    assert detalle["total_legajos"] == 5
    assert personas["total"] == 2
    assert sum(len(g["legajos"]) for g in detalle["grupos"]) == 1


def test_asignacion_y_custodia_no_cambian_el_resultado(cliente_api, tenant_de_prueba):
    ids = _sembrar(tenant_de_prueba)
    headers = tenant_de_prueba.headers("supervisor")
    antes = cliente_api.get(_url(), headers=headers).json()["items"]
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.asignacion_supervisor (tenant_id,sujeto_id,supervisor_usuario_id,desde,asignada_por) VALUES (:t,'persona-1',:u,'2026-01-01','test')"),
                  {"t": tenant_de_prueba.tenant_id, "u": tenant_de_prueba.usuarios["supervisor"]})
        s.execute(text("INSERT INTO modulo1.custodia_recurso (custodia_id,tenant_id,recurso_id,tipo_recurso) VALUES (:c,:t,'vehiculo-1','vehiculo')"),
                  {"c": ids["custodia"], "t": tenant_de_prueba.tenant_id})
        s.execute(text("INSERT INTO modulo1.periodo_custodia (tenant_id,custodia_id,custodio_id,desde) VALUES (:t,:c,'persona-1','2026-01-01')"),
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
