"""B-5: hooks secundarios de CargarDocumento no abortan la versión documental."""
from __future__ import annotations

from sqlalchemy import text

from app.db import tenant_session
from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar


def _vigente(t, sujeto: str, req: str) -> dict | None:
    with tenant_session(t.tenant_id) as s:
        fila = s.execute(text(
            "SELECT documento_id::text, estado_version, estado_confirmacion FROM modulo1.documento "
            "WHERE tenant_id = :t AND sujeto_id = :s AND requisito_definicion_id = :r AND estado_version = 'vigente'"
        ), {"t": t.tenant_id, "s": sujeto, "r": req}).mappings().first()
        return dict(fila) if fila else None


def test_carga_conserva_documento_si_registrar_accion_falla(cliente_api, tenant_de_prueba, monkeypatch):
    from app.modules.alertas import servicio as alertas

    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto savepoint")
    sujeto = _alta_persona(cliente_api, t, "savepoint-accion")

    def _falla(*_a, **_k):
        raise RuntimeError("simulación: alertas no disponibles")

    monkeypatch.setattr(alertas, "registrar_accion", _falla)
    doc = _cargar(cliente_api, t, sujeto, req)
    vigente = _vigente(t, sujeto, req)
    assert vigente is not None and vigente["documento_id"] == doc["documento_id"]
    assert "DocumentoCargado" in doc["eventos"]


def test_carga_conserva_documento_si_operadoras_falla(cliente_api, tenant_de_prueba, monkeypatch):
    from app.modules.operadoras import servicio as operadoras

    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto operadoras")
    sujeto = _alta_persona(cliente_api, t, "savepoint-operadoras")

    def _falla(*_a, **_k):
        raise RuntimeError("simulación: reconciliar operadoras")

    monkeypatch.setattr(operadoras, "al_registrar_nueva_version", _falla)
    doc = _cargar(cliente_api, t, sujeto, req)
    assert _vigente(t, sujeto, req)["documento_id"] == doc["documento_id"]


def test_carga_verificada_conserva_documento_si_resolver_alertas_falla(cliente_api, tenant_de_prueba, monkeypatch):
    from app.modules.alertas import servicio as alertas

    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Apto resolver")
    sujeto = _alta_persona(cliente_api, t, "savepoint-resolver")

    def _falla(*_a, **_k):
        raise RuntimeError("simulación: resolver_por_verificacion")

    monkeypatch.setattr(alertas, "resolver_por_verificacion", _falla)
    doc = _cargar(cliente_api, t, sujeto, req, estado_confirmacion="verificado")
    assert _vigente(t, sujeto, req)["estado_confirmacion"] == "verificado"
    assert "DocumentoVerificado" in doc["eventos"]
