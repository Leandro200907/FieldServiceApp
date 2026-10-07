"""Flujo real: responsable publica matrices desde plantilla (una versión, enlace a plantilla)."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_requisitos import _alta_def
from tests.test_h04_plantillas_globales import CMD, _copiar_matriz, catalogo  # noqa: F401

HOY = "2026-09-20"


def _clave():
    return {"cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()), "tipo_servicio_id": str(uuid.uuid4())}


def _lineas_desde_catalogo(cliente_api, t, catalogo, locacion_id: str) -> list[dict]:
    suf = catalogo["sufijo"]
    datos = catalogo["datos"]["matrices"][0]["lineas"]
    lineas = []
    for lg in datos:
        nombre = lg["definicion"]
        gid = catalogo["defs"][nombre]
        body = {"definicion_global_id": gid}
        if "Induccion" in nombre:
            body["locacion_id"] = locacion_id
        r = cliente_api.post(f"{CMD}/copiar_definicion_global", json=body, headers=t.headers("responsable_legajos"))
        assert r.status_code == 200, r.text
        rid = r.json()["requisito_definicion_id"]
        lineas.append({
            "requisito_definicion_id": rid,
            "clasificacion": lg["clasificacion"],
            "bloqueante_durante_ejecucion": lg["bloqueante_durante_ejecucion"],
        })
    return lineas


def _publicar(cliente_api, t, catalogo, lineas, **extra):
    clave = _clave()
    r = cliente_api.post(
        f"{CMD}/publicar_version_de_matriz",
        json={**clave, "vigente_desde": HOY, "lineas": lineas, "matriz_global_id": catalogo["matriz"], **extra},
        headers=t.headers("responsable_legajos"),
    )
    return r, clave


def test_responsable_plantilla_sin_cambios_una_version_enlazada(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    lineas = _lineas_desde_catalogo(cliente_api, t, catalogo, str(uuid.uuid4()))
    r, clave = _publicar(cliente_api, t, catalogo, lineas)
    assert r.status_code == 200, r.text
    with tenant_session(t.tenant_id) as s:
        filas = s.execute(text(
            "SELECT version, matriz_global_id, copiada_de_version FROM modulo1.matriz_requisitos "
            "WHERE tenant_id = :t AND cliente_id = :c AND locacion_id = :l AND tipo_servicio_id = :ts"
        ), {"t": t.tenant_id, "c": clave["cliente_id"], "l": clave["locacion_id"], "ts": clave["tipo_servicio_id"]}).all()
        n_lineas = s.execute(text(
            "SELECT count(*) FROM modulo1.linea_requisito l JOIN modulo1.matriz_requisitos m USING (tenant_id, matriz_version_id) "
            "WHERE m.tenant_id = :t AND m.cliente_id = :c"
        ), {"t": t.tenant_id, "c": clave["cliente_id"]}).scalar()
    assert len(filas) == 1 and filas[0][0] == 1
    assert str(filas[0][1]) == catalogo["matriz"] and filas[0][2] == 1
    assert n_lineas == 4


def test_responsable_plantilla_con_cambios_una_version_lineas_exactas(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    loc = str(uuid.uuid4())
    lineas = _lineas_desde_catalogo(cliente_api, t, catalogo, loc)
    extra = _alta_def(cliente_api, t, f"Extra local {catalogo['sufijo']}", "documento", "vehiculo")
    lineas[0]["clasificacion"] = "excepcionable"
    lineas[0]["bloqueante_durante_ejecucion"] = False
    lineas = [lineas[0], lineas[2], {"requisito_definicion_id": extra, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}]
    r, clave = _publicar(cliente_api, t, catalogo, lineas)
    assert r.status_code == 200, r.text
    with tenant_session(t.tenant_id) as s:
        mids = s.execute(text(
            "SELECT matriz_version_id::text FROM modulo1.matriz_requisitos WHERE tenant_id = :t AND cliente_id = :c"
        ), {"t": t.tenant_id, "c": clave["cliente_id"]}).scalars().all()
        det = s.execute(text(
            "SELECT l.requisito_definicion_id::text, l.clasificacion FROM modulo1.linea_requisito l "
            "WHERE l.tenant_id = :t AND l.matriz_version_id = :m ORDER BY l.clasificacion"
        ), {"t": t.tenant_id, "m": mids[0]}).all()
    assert len(mids) == 1
    assert len(det) == 3
    assert any(d[1] == "excepcionable" for d in det)
    assert extra in {d[0] for d in det}


def test_publicar_misma_vigente_desde_409_luego_posterior_200(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    lineas = _lineas_desde_catalogo(cliente_api, t, catalogo, str(uuid.uuid4()))
    r1, clave = _publicar(cliente_api, t, catalogo, lineas)
    assert r1.status_code == 200
    r2 = cliente_api.post(
        f"{CMD}/publicar_version_de_matriz",
        json={**clave, "vigente_desde": HOY, "lineas": lineas, "matriz_global_id": catalogo["matriz"]},
        headers=t.headers("responsable_legajos"),
    )
    assert r2.status_code == 409
    assert "mismo día" in r2.json()["error"]["mensaje"] or "antes" in r2.json()["error"]["mensaje"]
    r3 = cliente_api.post(
        f"{CMD}/publicar_version_de_matriz",
        json={**clave, "vigente_desde": "2026-10-01", "lineas": lineas, "matriz_global_id": catalogo["matriz"]},
        headers=t.headers("responsable_legajos"),
    )
    assert r3.status_code == 200, r3.text
    with tenant_session(t.tenant_id) as s:
        vers = s.execute(text(
            "SELECT version, vigente_hasta FROM modulo1.matriz_requisitos WHERE tenant_id = :t AND cliente_id = :c ORDER BY version"
        ), {"t": t.tenant_id, "c": clave["cliente_id"]}).all()
    from datetime import date
    assert vers == [(1, date(2026, 9, 30)), (2, None)]


def test_traer_con_hoy_200_misma_fecha_inicio_409(cliente_api, catalogo, tenant_de_prueba):
    t = tenant_de_prueba
    r0, body = _copiar_matriz(cliente_api, t, catalogo, vigente_desde="2026-01-01")
    assert r0.status_code == 200
    with tenant_session(t.tenant_id) as s:
        mv = s.execute(text("SELECT matriz_version_id::text FROM modulo1.matriz_requisitos WHERE tenant_id = :t AND cliente_id = :c"),
                       {"t": t.tenant_id, "c": body["cliente_id"]}).scalar()
        lineas = [dict(x) for x in s.execute(text(
            "SELECT requisito_definicion_id::text AS requisito_definicion_id, clasificacion, bloqueante_durante_ejecucion "
            "FROM modulo1.linea_requisito WHERE tenant_id = :t AND matriz_version_id = :m"), {"t": t.tenant_id, "m": mv}).mappings()]
    clave = {k: body[k] for k in ("cliente_id", "locacion_id", "tipo_servicio_id")}
    pub_hoy = cliente_api.post(
        f"{CMD}/publicar_version_de_matriz",
        json={**clave, "vigente_desde": HOY, "lineas": lineas, "matriz_global_id": catalogo["matriz"], "fuente": "traer test"},
        headers=t.headers("responsable_legajos"),
    )
    assert pub_hoy.status_code == 200, pub_hoy.text
    dup = cliente_api.post(
        f"{CMD}/publicar_version_de_matriz",
        json={**clave, "vigente_desde": "2026-01-01", "lineas": lineas, "matriz_global_id": catalogo["matriz"]},
        headers=t.headers("responsable_legajos"),
    )
    assert dup.status_code == 409
