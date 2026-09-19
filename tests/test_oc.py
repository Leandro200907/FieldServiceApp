"""Backlog de OC: ImportarLote (idempotente por lote_id, upsert por clave_origen,
rechazo por fila) y CancelarOC. Contra base real."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session

CLIENTE, LOCACION, TIPO = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def _fila(clave: str, desde: str = "2026-01-01", hasta: str = "2026-12-31", **extra) -> dict:
    base = {
        "clave_origen": clave,
        "referencia": f"OC {clave}",
        "cliente_id": CLIENTE,
        "locacion_id": LOCACION,
        "tipo_servicio_id": TIPO,
        "vigencia_desde": desde,
        "vigencia_hasta": hasta,
    }
    base.update(extra)
    return base


def _importar(cliente_api, tenant, lote_id, filas, rol="responsable_legajos"):
    return cliente_api.post(
        "/v1/comandos/importar_lote_oc",
        json={"lote_id": lote_id, "origen": "planilla", "filas": filas},
        headers=tenant.headers(rol),
    )


def _contar(tenant, sql: str, **params) -> int:
    with tenant_session(tenant.tenant_id) as s:
        return s.execute(text(sql), params).scalar()


def test_importar_lote_es_idempotente_por_lote_id(cliente_api, tenant_de_prueba):
    lote = str(uuid.uuid4())
    r1 = _importar(cliente_api, tenant_de_prueba, lote, [_fila("OC-1"), _fila("OC-2")])
    assert r1.status_code == 200, r1.text
    cuerpo = r1.json()
    assert cuerpo["filas_aceptadas"] == 2 and cuerpo["oc_creadas"] == 2
    assert cuerpo["eventos"] == ["LoteAplicado"]

    # Mismo lote_id con contenido distinto: 409, no un replay silencioso (A-03). Nada se aplica.
    r_dist = _importar(cliente_api, tenant_de_prueba, lote, [_fila("OC-1"), _fila("OC-2"), _fila("OC-3")])
    assert r_dist.status_code == 409 and r_dist.json()["error"]["codigo"] == "clave_idempotencia_reutilizada"
    # Mismo lote_id y mismo contenido: replay exacto, sin re-aplicar.
    r2 = _importar(cliente_api, tenant_de_prueba, lote, [_fila("OC-1"), _fila("OC-2")])
    assert r2.status_code == 200
    assert r2.json()["oc_ids"] == cuerpo["oc_ids"]
    assert _contar(tenant_de_prueba, "SELECT count(*) FROM modulo1.oc") == 2
    assert _contar(tenant_de_prueba, "SELECT count(*) FROM modulo1.lote_importacion") == 1
    assert _contar(tenant_de_prueba, "SELECT count(*) FROM modulo1.event_log WHERE tipo = 'LoteAplicado'") == 1


def test_upsert_por_clave_origen_actualiza_en_vez_de_duplicar(cliente_api, tenant_de_prueba):
    r1 = _importar(cliente_api, tenant_de_prueba, str(uuid.uuid4()), [_fila("OC-7", hasta="2026-06-30")])
    assert r1.status_code == 200, r1.text
    oc_id = r1.json()["oc_ids"][0]

    r2 = _importar(cliente_api, tenant_de_prueba, str(uuid.uuid4()), [_fila("OC-7", hasta="2026-09-30", referencia="nueva")])
    assert r2.status_code == 200, r2.text
    assert r2.json()["oc_creadas"] == 0 and r2.json()["oc_actualizadas"] == 1
    assert r2.json()["oc_ids"] == [oc_id]

    with tenant_session(tenant_de_prueba.tenant_id) as s:
        filas = s.execute(
            text("SELECT oc_id, referencia, vigencia_hasta, actualizado_en > creado_en AS tocada FROM modulo1.oc WHERE clave_origen = 'OC-7'")
        ).all()
    assert len(filas) == 1
    assert str(filas[0][0]) == oc_id
    assert filas[0][1] == "nueva" and str(filas[0][2]) == "2026-09-30" and filas[0][3] is True


def test_filas_invalidas_se_rechazan_con_detalle(cliente_api, tenant_de_prueba):
    filas = [
        _fila("OK-1"),
        _fila("MAL-FECHAS", desde="2026-12-31", hasta="2026-01-01"),
        {"clave_origen": "MAL-FALTA", "cliente_id": CLIENTE},
        _fila("MAL-UUID", cliente_id="no-es-uuid"),
        _fila("OK-1"),  # repetida en el lote
    ]
    r = _importar(cliente_api, tenant_de_prueba, str(uuid.uuid4()), filas)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["filas_totales"] == 5 and cuerpo["filas_aceptadas"] == 1 and cuerpo["filas_rechazadas"] == 4
    motivos = {d["clave_origen"]: d["motivo"] for d in cuerpo["detalle_filas_rechazadas"]}
    assert "invertida" in motivos["MAL-FECHAS"]
    assert "faltantes" in motivos["MAL-FALTA"]
    assert "UUID" in motivos["MAL-UUID"]
    assert "repetida" in motivos["OK-1"]
    with tenant_session(tenant_de_prueba.tenant_id) as s:
        lote = s.execute(text("SELECT filas_rechazadas, detalle_filas_rechazadas FROM modulo1.lote_importacion")).first()
    assert lote[0] == 4 and len(lote[1]) == 4
    assert _contar(tenant_de_prueba, "SELECT count(*) FROM modulo1.oc") == 1


def test_importar_lote_exige_responsable_legajos(cliente_api, tenant_de_prueba):
    r = _importar(cliente_api, tenant_de_prueba, str(uuid.uuid4()), [_fila("X")], rol="supervisor")
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "prohibido"


def test_cancelar_oc(cliente_api, tenant_de_prueba):
    r = _importar(cliente_api, tenant_de_prueba, str(uuid.uuid4()), [_fila("OC-C")])
    oc_id = r.json()["oc_ids"][0]
    r = cliente_api.post(
        "/v1/comandos/cancelar_oc", json={"oc_id": oc_id}, headers=tenant_de_prueba.headers("responsable_legajos", "k-1")
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "cancelado"
    assert _contar(tenant_de_prueba, "SELECT count(*) FROM modulo1.oc WHERE estado = 'cancelado'") == 1
    # Misma Idempotency-Key → mismo resultado, sin 409.
    r = cliente_api.post(
        "/v1/comandos/cancelar_oc", json={"oc_id": oc_id}, headers=tenant_de_prueba.headers("responsable_legajos", "k-1")
    )
    assert r.status_code == 200 and r.json()["estado"] == "cancelado"
    # Sin clave, cancelar dos veces es conflicto.
    r = cliente_api.post("/v1/comandos/cancelar_oc", json={"oc_id": oc_id}, headers=tenant_de_prueba.headers("responsable_legajos"))
    assert r.status_code == 409
    # Inexistente.
    r = cliente_api.post(
        "/v1/comandos/cancelar_oc", json={"clave_origen": "NO-EXISTE"}, headers=tenant_de_prueba.headers("responsable_legajos")
    )
    assert r.status_code == 404
