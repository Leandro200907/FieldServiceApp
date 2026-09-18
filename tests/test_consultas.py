"""Consultas GET /v1/consultas/*: alcance por rol, bordes inclusive de vigencia,
paginación y cobertura de OC. Contra base real; datos de apoyo por SQL directo."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.comun.reloj import hoy_del_tenant
from app.db import tenant_session

CLIENTE, LOCACION, TIPO = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


# --------------------------------------------------------------------- apoyo


def _hoy(tenant):
    with tenant_session(tenant.tenant_id) as s:
        return hoy_del_tenant(s, tenant.tenant_id)


def _legajo(s, tenant, sujeto_id, tipo="persona"):
    s.execute(
        text(
            "INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) "
            "VALUES (:t, :s, :tipo, :s)"
        ),
        {"t": tenant.tenant_id, "s": sujeto_id, "tipo": tipo},
    )


def _requisito(s, tenant, nombre="Carnet", tipo_sujeto="persona") -> str:
    rid = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.definicion_requisito (requisito_definicion_id, tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
            "VALUES (:id, :t, :n, 'documento', :ts)"
        ),
        {"id": rid, "t": tenant.tenant_id, "n": nombre, "ts": tipo_sujeto},
    )
    return rid


def _documento(s, tenant, sujeto_id, requisito_id, desde, hasta, **extra) -> str:
    did = str(uuid.uuid4())
    campos = {
        "estado_confirmacion": "verificado",
        "estado_version": "vigente",
        "origen_propuesta": False,
        "origen": "carga_manual",
    }
    campos.update(extra)
    s.execute(
        text(
            "INSERT INTO modulo1.documento (documento_id, tenant_id, sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, "
            "estado_confirmacion, estado_version, origen_propuesta, origen) "
            "VALUES (:id, :t, :s, :r, :d, :h, :ec, :ev, :op, :o)"
        ),
        {"id": did, "t": tenant.tenant_id, "s": sujeto_id, "r": requisito_id, "d": desde, "h": hasta,
         "ec": campos["estado_confirmacion"], "ev": campos["estado_version"], "op": campos["origen_propuesta"], "o": campos["origen"]},
    )
    return did


def _asignar_supervisor(s, tenant, sujeto_id, desde, supervisor_usuario_id=None):
    s.execute(
        text(
            "INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
            "VALUES (:t, :s, :u, :d, 'test')"
        ),
        {"t": tenant.tenant_id, "s": sujeto_id, "u": supervisor_usuario_id or tenant.usuarios["supervisor"], "d": desde},
    )


def _matriz(s, tenant, version, desde, hasta, requisitos: list[str]) -> str:
    mid = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.matriz_requisitos (matriz_version_id, tenant_id, cliente_id, locacion_id, tipo_servicio_id, version, vigente_desde, vigente_hasta) "
            "VALUES (:id, :t, :c, :l, :ts, :v, :d, :h)"
        ),
        {"id": mid, "t": tenant.tenant_id, "c": CLIENTE, "l": LOCACION, "ts": TIPO, "v": version, "d": desde, "h": hasta},
    )
    for rid in requisitos:
        s.execute(
            text(
                "INSERT INTO modulo1.linea_requisito (matriz_version_id, requisito_definicion_id, tenant_id, clasificacion, bloqueante_durante_ejecucion) "
                "VALUES (:m, :r, :t, 'bloqueante_duro', true)"
            ),
            {"m": mid, "r": rid, "t": tenant.tenant_id},
        )
    return mid


def _oc(s, tenant, clave, desde, hasta):
    s.execute(
        text(
            "INSERT INTO modulo1.oc (tenant_id, clave_origen, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta) "
            "VALUES (:t, :c, :cli, :loc, :ts, :d, :h)"
        ),
        {"t": tenant.tenant_id, "c": clave, "cli": CLIENTE, "loc": LOCACION, "ts": TIPO, "d": desde, "h": hasta},
    )


# --------------------------------------------------------------------- legajo


def test_legajo_del_tecnico_ajeno_es_403(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    hoy = _hoy(t)
    with tenant_session(t.tenant_id) as s:
        _legajo(s, t, t.sujeto_tecnico)
        _legajo(s, t, "persona_otra")
        rid = _requisito(s, t)
        _documento(s, t, t.sujeto_tecnico, rid, hoy - timedelta(days=10), hoy)
    # El propio: OK, y el documento que vence hoy sigue vigente (borde inclusive).
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": t.sujeto_tecnico}, headers=t.headers("tecnico"))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["legajo"]["sujeto_id"] == t.sujeto_tecnico
    assert len(cuerpo["documentos"]) == 1
    doc = cuerpo["documentos"][0]
    assert doc["vigente_hoy"] is True and doc["dias_para_vencer"] == 0 and doc["estado_confirmacion"] == "verificado"
    # El ajeno: prohibido, aunque exista.
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": "persona_otra"}, headers=t.headers("tecnico"))
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "prohibido"
    # responsable_legajos lo ve.
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": "persona_otra"}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200
    # Inexistente → 404.
    r = cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": "nadie"}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 404


def test_propuestas_pendientes(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    hoy = _hoy(t)
    with tenant_session(t.tenant_id) as s:
        rid = _requisito(s, t)
        _documento(s, t, "p1", rid, hoy, hoy + timedelta(days=30), origen_propuesta=True, estado_confirmacion="declarado")
        _documento(s, t, "p2", rid, hoy, hoy + timedelta(days=30), origen_propuesta=True, estado_confirmacion="verificado")
        _documento(s, t, "p3", rid, hoy, hoy + timedelta(days=30), origen_propuesta=False, estado_confirmacion="declarado")
    r = cliente_api.get("/v1/consultas/propuestas_pendientes", headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1 and r.json()["items"][0]["sujeto_id"] == "p1"
    r = cliente_api.get("/v1/consultas/propuestas_pendientes", headers=t.headers("supervisor"))
    assert r.status_code == 403


# --------------------------------------------------------------------- tablero


def test_tablero_incluye_vencidos_y_proximos_con_borde_inclusive(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    hoy = _hoy(t)
    with tenant_session(t.tenant_id) as s:
        rid = _requisito(s, t)
        r2 = _requisito(s, t, "Otro")
        r3 = _requisito(s, t, "Lejano")
        _documento(s, t, "p1", rid, hoy - timedelta(days=400), hoy - timedelta(days=5))  # vencido
        _documento(s, t, "p1", r2, hoy - timedelta(days=10), hoy)  # vence hoy
        _documento(s, t, "p2", rid, hoy, hoy + timedelta(days=30))  # justo en el límite
        _documento(s, t, "p2", r3, hoy, hoy + timedelta(days=31))  # fuera
    r = cliente_api.get("/v1/consultas/tablero_vencimientos", params={"dias": 30}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["total"] == 3
    dias = [i["dias_para_vencer"] for i in cuerpo["items"]]
    assert dias == [-5, 0, 30]  # ordenado por vigente_hasta
    assert [i["vencido"] for i in cuerpo["items"]] == [True, False, False]
    assert [i["vigente_hoy"] for i in cuerpo["items"]] == [False, True, True]


def test_supervisor_ve_solo_su_universo_en_tablero(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    hoy = _hoy(t)
    with tenant_session(t.tenant_id) as s:
        rid = _requisito(s, t)
        _documento(s, t, "p_mio", rid, hoy, hoy + timedelta(days=3))
        _documento(s, t, "p_ajeno", rid, hoy, hoy + timedelta(days=3))
        _documento(s, t, "p_cerrado", rid, hoy, hoy + timedelta(days=3))
        _asignar_supervisor(s, t, "p_mio", hoy)
        _asignar_supervisor(s, t, "p_ajeno", hoy, supervisor_usuario_id=t.usuarios["configuracion"])
        # Asignación cerrada: ya no forma parte del universo.
        s.execute(
            text(
                "INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, hasta, estado, asignada_por) "
                "VALUES (:t, 'p_cerrado', :u, :d, :d, 'cerrada', 'test')"
            ),
            {"t": t.tenant_id, "u": t.usuarios["supervisor"], "d": hoy - timedelta(days=1)},
        )
    r = cliente_api.get("/v1/consultas/tablero_vencimientos", params={"dias": 30}, headers=t.headers("supervisor"))
    assert r.status_code == 200, r.text
    assert [i["sujeto_id"] for i in r.json()["items"]] == ["p_mio"]
    r = cliente_api.get("/v1/consultas/tablero_vencimientos", params={"dias": 30}, headers=t.headers("responsable_legajos"))
    assert r.json()["total"] == 3
    # El supervisor también puede ver el legajo de su universo, y no el ajeno.
    with tenant_session(t.tenant_id) as s:
        _legajo(s, t, "p_mio")
        _legajo(s, t, "p_ajeno")
    assert cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": "p_mio"}, headers=t.headers("supervisor")).status_code == 200
    assert cliente_api.get("/v1/consultas/legajo", params={"sujeto_id": "p_ajeno"}, headers=t.headers("supervisor")).status_code == 403
    assert cliente_api.get("/v1/consultas/tablero_vencimientos", headers=t.headers("tecnico")).status_code == 403


# --------------------------------------------------------------------- matriz


def test_matriz_vigente_con_fecha_igual_a_vigente_hasta(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        rid = _requisito(s, t)
        v1 = _matriz(s, t, 1, "2026-01-01", "2026-06-30", [rid])
        v2 = _matriz(s, t, 2, "2026-07-01", None, [rid])
    params = {"cliente_id": CLIENTE, "locacion_id": LOCACION, "tipo_servicio_id": TIPO}
    r = cliente_api.get("/v1/consultas/matriz_vigente", params={**params, "fecha": "2026-06-30"}, headers=t.headers("tecnico"))
    assert r.status_code == 200, r.text
    assert r.json()["matriz_version_id"] == v1 and r.json()["version"] == 1
    assert len(r.json()["lineas"]) == 1 and r.json()["lineas"][0]["requisito"] == "Carnet"
    r = cliente_api.get("/v1/consultas/matriz_vigente", params={**params, "fecha": "2026-07-01"}, headers=t.headers("tecnico"))
    assert r.json()["matriz_version_id"] == v2
    r = cliente_api.get("/v1/consultas/matriz_vigente", params={**params, "fecha": "2025-12-31"}, headers=t.headers("tecnico"))
    assert r.status_code == 404


# --------------------------------------------------------------------- auditoría / supervisión


def test_log_auditoria_paginado(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        for i in range(7):
            s.execute(
                text("INSERT INTO modulo1.event_log (tenant_id, tipo, payload) VALUES (:t, :tipo, CAST(:p AS jsonb))"),
                {"t": t.tenant_id, "tipo": "DocumentoCargado" if i % 2 == 0 else "LegajoCreado", "p": '{"n": %d}' % i},
            )
    r = cliente_api.get("/v1/consultas/log_auditoria", params={"limit": 3}, headers=t.headers("configuracion"))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["total"] == 7 and cuerpo["limit"] == 3 and len(cuerpo["items"]) == 3
    assert [i["payload"]["n"] for i in cuerpo["items"]] == [6, 5, 4]  # más reciente primero
    r = cliente_api.get("/v1/consultas/log_auditoria", params={"limit": 3, "offset": 6}, headers=t.headers("configuracion"))
    assert [i["payload"]["n"] for i in r.json()["items"]] == [0]
    r = cliente_api.get("/v1/consultas/log_auditoria", params={"tipo": "LegajoCreado"}, headers=t.headers("responsable_legajos"))
    assert r.json()["total"] == 3
    assert cliente_api.get("/v1/consultas/log_auditoria", headers=t.headers("supervisor")).status_code == 403


def test_historial_supervision(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    hoy = _hoy(t)
    with tenant_session(t.tenant_id) as s:
        s.execute(
            text(
                "INSERT INTO modulo1.asignacion_supervisor (tenant_id, sujeto_id, supervisor_usuario_id, desde, hasta, estado, asignada_por) "
                "VALUES (:t, 'p1', :u, :d, :h, 'cerrada', 'test')"
            ),
            {"t": t.tenant_id, "u": t.usuarios["configuracion"], "d": hoy - timedelta(days=100), "h": hoy - timedelta(days=1)},
        )
        _asignar_supervisor(s, t, "p1", hoy)
    r = cliente_api.get("/v1/consultas/historial_supervision", params={"sujeto_id": "p1"}, headers=t.headers("configuracion"))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [i["estado"] for i in items] == ["cerrada", "vigente"]
    assert items[1]["supervisor_usuario_id"] == t.usuarios["supervisor"] and items[1]["supervisor_nombre"] == "supervisor"
    assert cliente_api.get("/v1/consultas/historial_supervision", params={"sujeto_id": "p1"}, headers=t.headers("supervisor")).status_code == 403


# --------------------------------------------------------------------- OC


def test_backlog_oc_con_ultima_evaluacion(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        _oc(s, t, "OC-A", "2026-01-01", "2026-12-31")
        _oc(s, t, "OC-B", "2026-02-01", "2026-12-31")
        s.execute(text("UPDATE modulo1.oc SET estado = 'cancelado' WHERE clave_origen = 'OC-B'"))
        for veredicto in ("no_habilitado", "habilitado"):  # la segunda es la última
            s.execute(
                text(
                    "INSERT INTO modulo1.evaluacion_habilitacion (tenant_id, commitment_id, veredicto_de_cumplimiento, resultado_de_decision, por_sujeto, snapshot, creado_en) "
                    "VALUES (:t, 'OC-A', :v, :r, '[]', '{}', now() + make_interval(secs => :s))"
                ),
                {"t": t.tenant_id, "v": veredicto, "r": "no_puede_asignarse" if veredicto == "no_habilitado" else "puede_asignarse", "s": 1 if veredicto == "habilitado" else 0},
            )
    r = cliente_api.get("/v1/consultas/backlog_oc", headers=t.headers("supervisor"))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    item = r.json()["items"][0]
    assert item["clave_origen"] == "OC-A" and item["ultima_evaluacion"]["veredicto_de_cumplimiento"] == "habilitado"
    r = cliente_api.get("/v1/consultas/backlog_oc", params={"estado": "cancelado"}, headers=t.headers("responsable_legajos"))
    assert r.json()["total"] == 1 and r.json()["items"][0]["ultima_evaluacion"] is None
    r = cliente_api.get("/v1/consultas/backlog_oc", params={"estado": ""}, headers=t.headers("responsable_legajos"))
    assert r.json()["total"] == 2
    # Cobertura sin recalcular devuelve la última persistida.
    r = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-A"}, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    assert r.json()["veredicto_de_cumplimiento"] == "habilitado" and r.json()["recalculada"] is False
    assert cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-B"}, headers=t.headers("responsable_legajos")).status_code == 404
    assert cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "NADA"}, headers=t.headers("responsable_legajos")).status_code == 404


def test_cobertura_oc_recalcular(cliente_api, tenant_de_prueba):
    from app.modules.consultas import servicio

    if not servicio.ORQUESTACION_DISPONIBLE:
        pytest.skip("app.core.orquestacion.evaluar_compromiso todavía no existe")
    t = tenant_de_prueba
    hoy = _hoy(t)
    with tenant_session(t.tenant_id) as s:
        _legajo(s, t, "empresa_1", tipo="empresa")
        _legajo(s, t, "p1")
        rid = _requisito(s, t, "Carnet", "persona")
        _matriz(s, t, 1, hoy - timedelta(days=30), None, [rid])
        _documento(s, t, "p1", rid, hoy - timedelta(days=10), hoy + timedelta(days=365))
        _oc(s, t, "OC-R", hoy, hoy + timedelta(days=10))
    r = cliente_api.get(
        "/v1/consultas/cobertura_oc", params={"commitment_id": "OC-R", "recalcular": "true"}, headers=t.headers("supervisor")
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["recalculada"] is True
    assert cuerpo["veredicto_de_cumplimiento"] in ("habilitado", "vence_durante_el_trabajo", "no_habilitado", "requiere_revision")
    assert cuerpo["resultado_de_decision"] in ("puede_asignarse", "puede_asignarse_bajo_excepcion", "no_puede_asignarse")
    assert cuerpo["por_sujeto"] is not None and cuerpo["requisitos_faltantes"] is not None
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.evaluacion_habilitacion WHERE commitment_id = 'OC-R'")).scalar() == 1
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'EvaluacionDeHabilitacionRealizada'")).scalar() == 1
    # Sin recalcular, ahora devuelve la recién persistida.
    r = cliente_api.get("/v1/consultas/cobertura_oc", params={"commitment_id": "OC-R"}, headers=t.headers("supervisor"))
    assert r.json()["referencia_evaluacion"] == cuerpo["referencia_evaluacion"]
