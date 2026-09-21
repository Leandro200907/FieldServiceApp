"""H-03: una fila sintácticamente inválida (UUID, fecha, campo obligatorio) NO hace fallar
el lote: se registra como rechazada (`fila_invalida`) en `detalle_filas_rechazadas` y las
demás se aplican, en una sola transacción (2.11 de modelo-dominio.md)."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _docs, _ok, _post


def _lote(cliente_api, t, filas, lote_id=None):
    return _post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": lote_id or str(uuid.uuid4()), "filas": filas})


def test_fila_con_uuid_fecha_o_campo_invalido_se_rechaza_sola_y_las_demas_se_aplican(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto médico")
    p1 = _alta_persona(cliente_api, t, "DNI 21")
    p2 = _alta_persona(cliente_api, t, "DNI 22")
    filas = [
        {"sujeto_id": p1, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},      # válida
        {"sujeto_id": p2, "requisito_definicion_id": "no-es-un-uuid", "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},  # UUID inválido
        {"sujeto_id": p2, "requisito_definicion_id": req, "vigente_desde": "31/12/2026", "vigente_hasta": "2026-12-31"},      # fecha malformada
        {"sujeto_id": p2, "requisito_definicion_id": req, "vigente_desde": "2026-01-01"},                                       # falta vigente_hasta
        {"sujeto_id": "", "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},       # campo vacío
        "esto no es una fila",                                                                                                  # ni siquiera un objeto
        {"sujeto_id": p2, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},      # válida
        {"sujeto_id": "persona_no_existe", "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},  # error de dominio
    ]
    r = _lote(cliente_api, t, filas)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert (cuerpo["filas_totales"], cuerpo["filas_aceptadas"], cuerpo["filas_rechazadas"]) == (8, 2, 6)
    rechazadas = {f["fila"]: f for f in cuerpo["detalle_filas_rechazadas"]}
    assert sorted(rechazadas) == [1, 2, 3, 4, 5, 7]
    assert all(rechazadas[i]["codigo"] == "fila_invalida" for i in (1, 2, 3, 4, 5))
    assert rechazadas[7]["codigo"] == "no_encontrado"
    assert rechazadas[1]["detalles"][0]["campo"] == "requisito_definicion_id"
    assert rechazadas[2]["detalles"][0]["campo"] == "vigente_desde"
    assert rechazadas[3]["detalles"][0]["campo"] == "vigente_hasta" and rechazadas[3]["detalles"][0]["tipo"] == "missing"
    assert rechazadas[4]["detalles"][0]["campo"] == "sujeto_id"
    assert "no-es-un-uuid" not in str(rechazadas[1]["detalles"])          # sin el input en el detalle
    assert [d["fila"] for d in cuerpo["documentos"]] == [0, 6]
    assert len(_docs(t, p1, req)) == 1 and len(_docs(t, p2, req)) == 1
    with tenant_session(t.tenant_id) as s:
        lote = s.execute(text("SELECT estado, filas_totales, filas_aceptadas, filas_rechazadas, detalle_filas_rechazadas "
                              "FROM modulo1.lote_importacion WHERE lote_id = :l"), {"l": cuerpo["lote_id"]}).mappings().one()
    assert (lote["estado"], lote["filas_totales"], lote["filas_aceptadas"], lote["filas_rechazadas"]) == ("aplicado", 8, 2, 6)
    assert len(lote["detalle_filas_rechazadas"]) == 6


def test_lote_con_todas_las_filas_invalidas_queda_registrado_sin_documentos(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    r = _ok(_lote(cliente_api, t, [{"sujeto_id": "x"}, {"vigente_desde": "ayer"}]))
    assert (r["filas_totales"], r["filas_aceptadas"], r["filas_rechazadas"]) == (2, 0, 2) and r["documentos"] == []
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.lote_importacion WHERE lote_id = :l"), {"l": r["lote_id"]}).scalar() == 1


def test_lote_vacio_o_sin_lista_sigue_siendo_422_del_request(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    assert _lote(cliente_api, t, []).status_code == 422
    assert _post(cliente_api, t, "responsable_legajos", "importar_lote", {"lote_id": str(uuid.uuid4()), "filas": "no"}).status_code == 422


def test_fila_invalida_forma_parte_del_contenido_idempotente(cliente_api, tenant_de_prueba):
    """Mismo lote_id, misma fila inválida → replay; una fila inválida distinta → 409."""
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto")
    p1 = _alta_persona(cliente_api, t, "DNI 23")
    lote_id = str(uuid.uuid4())
    filas = [{"sujeto_id": p1, "requisito_definicion_id": req, "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"},
             {"sujeto_id": p1, "requisito_definicion_id": "malo", "vigente_desde": "2026-01-01", "vigente_hasta": "2026-12-31"}]
    r1 = _ok(_lote(cliente_api, t, filas, lote_id))
    assert _ok(_lote(cliente_api, t, filas, lote_id)) == r1
    r3 = _lote(cliente_api, t, filas[:1] + [{**filas[1], "requisito_definicion_id": "otro-malo"}], lote_id)
    assert r3.status_code == 409
    assert len(_docs(t, p1, req)) == 1
