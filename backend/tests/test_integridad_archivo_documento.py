"""B-3: restaurar sucedido y reconciliación de archivos."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from scripts.reconciliar_archivos_documento import reconciliar
from tests import apoyo
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _post, _ok


def test_rechazar_propuesta_no_restaura_sucedido_sin_archivo_en_storage(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto restaurar")
    p = _alta_persona(cliente_api, t, "restaurar", sujeto_id=t.sujeto_tecnico)
    v1 = _cargar(cliente_api, t, p, req, desde="2026-01-01", hasta="2026-12-31")
    prop = _ok(_post(cliente_api, t, "tecnico", "proponer_documento", {
        "sujeto_id": p, "requisito_definicion_id": req, "vigente_desde": "2026-02-01", "vigente_hasta": "2027-12-31",
    }))
    did_v1 = v1["documento_id"]
    with tenant_session(t.tenant_id) as s:
        s.execute(text(
            "UPDATE modulo1.documento SET clave_storage = :c, archivo_estado = 'confirmado', checksum_archivo = 'x', "
            "archivo_bytes = 1 WHERE documento_id = :d"
        ), {"c": f"{t.tenant_id}/{did_v1}/fantasma.pdf", "d": did_v1})
    _ok(_post(cliente_api, t, "responsable_legajos", "rechazar_propuesta",
              {"documento_id": prop["documento_id"], "motivo": "no"}))
    with tenant_session(t.tenant_id) as s:
        vigente = s.execute(text(
            "SELECT documento_id::text FROM modulo1.documento WHERE tenant_id = :t AND sujeto_id = :s "
            "AND requisito_definicion_id = :r AND estado_version = 'vigente'"
        ), {"t": t.tenant_id, "s": p, "r": req}).scalar()
        assert vigente == did_v1


def test_reconciliar_reporta_confirmado_sin_objeto(tenant_de_prueba):
    t = tenant_de_prueba.tenant_id
    did = str(uuid.uuid4())
    with tenant_session(t) as s:
        apoyo.legajo(s, t, "persona_rec")
        req = str(uuid.uuid4())
        s.execute(text(
            "INSERT INTO modulo1.definicion_requisito (requisito_definicion_id, tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
            "VALUES (:r, :t, 'X', 'documento', 'persona')"
        ), {"r": req, "t": t})
        s.execute(text(
            "INSERT INTO modulo1.documento (documento_id, tenant_id, sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, "
            "origen, estado_version, clave_storage, archivo_estado, checksum_archivo, archivo_bytes) "
            "VALUES (:d, :t, 'persona_rec', :r, '2026-01-01', '2026-12-31', 'carga_manual', 'vigente', :c, 'confirmado', 'x', 1)"
        ), {"d": did, "t": t, "r": req, "c": f"{t}/{did}/ausente.pdf"})
    r = reconciliar(t, aplicar=False)
    assert r["faltantes"] == 1
    r2 = reconciliar(t, aplicar=True)
    assert r2["corregidos"] == 1
    with tenant_session(t) as s:
        fila = s.execute(text(
            "SELECT archivo_estado, clave_storage, archivo_validacion FROM modulo1.documento WHERE documento_id = :d"
        ), {"d": did}).one()
        assert fila == ("sin_archivo", None, "invalido")
